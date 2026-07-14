"""
Quiz generation and management service.

Follows the flashcard_service.py pattern:
  - Gemini integration for quiz generation
  - Parsing with clean_gemini_response / parse_quiz_json
  - Chunk batching
  - CRUD with ownership enforcement
  - Attempt submission, scoring, and review
"""
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_question import QuizQuestion
from app.services.llm_service import generate as gemini_generate
from app.services.prompt_service import (
    QUIZ_SYSTEM_INSTRUCTION,
    format_quiz_prompt,
)
from app.services.cache_service import invalidate_search_cache
from app.core.logging import get_logger

logger = get_logger("app.services.quiz")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BATCH_SIZE = settings.QUIZ_BATCH_SIZE
_MAX_PER_BATCH = settings.QUIZ_MAX_PER_BATCH
_QUIZ_MODEL = settings.QUIZ_MODEL
_QUIZ_TIMEOUT = settings.QUIZ_TIMEOUT_SECONDS
_DEFAULT_QUESTION_COUNT = settings.QUIZ_DEFAULT_QUESTION_COUNT

# Pattern to strip markdown code fences from Gemini output
_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?```",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def clean_gemini_response(text: str) -> str:
    """Strip code fences, markdown, and leading/trailing noise from Gemini output.

    1. Remove ```json ... ``` or ``` ... ``` code fences.
    2. Strip any surrounding whitespace.
    3. If the result doesn't start with '[' or '{', try to find the first
       '[' or '{' and discard everything before it.
    4. Remove trailing noise after the last ']' or '}'.
    """
    # Remove code fences
    match = _CODE_FENCE_PATTERN.search(text)
    if match:
        text = match.group(1)

    text = text.strip()

    # Find first JSON character if text starts with noise
    if text and text[0] not in ("[", "{"):
        for prefix in ("[", "{"):
            idx = text.find(prefix)
            if idx != -1:
                text = text[idx:]
                break

    # Remove trailing noise after the last ] or }
    if text:
        last_bracket = text.rfind("]")
        last_brace = text.rfind("}")
        last_valid = max(last_bracket, last_brace)
        if last_valid != -1:
            text = text[: last_valid + 1]

    return text.strip()


def parse_quiz_json(text: str) -> list[dict[str, Any]]:
    """Parse cleaned Gemini output as a JSON array of quiz question objects.

    Returns:
        List of parsed question dicts. If parsing fails, returns an empty list
        and logs the warning -- never raises.
    """
    cleaned = clean_gemini_response(text)
    if not cleaned:
        logger.warning("Gemini returned empty response after cleaning")
        return []

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini output is not valid JSON: %s | text=%.200s", exc, cleaned)
        return []

    if isinstance(parsed, dict):
        # Single object wrapped in dict instead of array
        parsed = [parsed]

    if not isinstance(parsed, list):
        logger.warning("Gemini output is not a list: type=%s", type(parsed).__name__)
        return []

    return parsed


def validate_question(q: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a single quiz question dict.

    Required fields:
        - type: must be 'multiple_choice', 'true_false', or 'short_answer'
        - question: non-empty string
        - correct_answer: non-empty string
        - explanation: non-empty string

    For multiple_choice: options must be a list of 4 strings.

    Returns the validated question dict with normalized keys, or None if invalid.
    """
    q_type = q.get("type", "").strip().lower()
    question_text = q.get("question", "").strip()
    correct_answer = str(q.get("correct_answer", "")).strip()
    explanation = q.get("explanation", "").strip()

    if q_type not in ("multiple_choice", "true_false", "short_answer"):
        logger.debug("Discarded question: invalid type '%s'", q_type)
        return None

    if not question_text:
        logger.debug("Discarded question: empty question text")
        return None

    if not correct_answer:
        logger.debug("Discarded question: empty correct_answer")
        return None

    if not explanation:
        logger.debug("Discarded question: empty explanation")
        return None

    options = q.get("options")
    if q_type == "multiple_choice":
        if not isinstance(options, list) or len(options) != 4:
            logger.debug("Discarded MCQ: need exactly 4 options, got %s", type(options).__name__ if not isinstance(options, list) else len(options))
            return None
        # Normalize options to strings
        options = [str(o).strip() for o in options]
        if not all(options):
            logger.debug("Discarded MCQ: empty option string")
            return None

    return {
        "type": q_type,
        "question": question_text,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "options": options if q_type == "multiple_choice" else None,
    }


# ---------------------------------------------------------------------------
# Chunk batching
# ---------------------------------------------------------------------------


def batch_chunks(chunks: list[Chunk], batch_size: int = _BATCH_SIZE) -> list[list[Chunk]]:
    """Group chunks into batches for Gemini requests."""
    return [chunks[i: i + batch_size] for i in range(0, len(chunks), batch_size)]


# ---------------------------------------------------------------------------
# Ownership helpers
# ---------------------------------------------------------------------------


def _get_document_or_404(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> Document:
    """Get a document by ID, verifying ownership. Raises 404 if not found."""
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


def _get_quiz_or_404(db: Session, quiz_id: uuid.UUID, user_id: uuid.UUID) -> Quiz:
    """Get a quiz by ID, verifying ownership. Raises 404 if not found."""
    quiz = (
        db.query(Quiz)
        .filter(Quiz.id == quiz_id, Quiz.user_id == user_id)
        .first()
    )
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )
    return quiz


# ---------------------------------------------------------------------------
# Quiz generation
# ---------------------------------------------------------------------------


def generate_quiz(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    question_count: int = _DEFAULT_QUESTION_COUNT,
) -> dict[str, Any]:
    """Generate a quiz from a document's chunks via Gemini.

    Flows:
        1. Verify document exists and belongs to user.
        2. Load all chunks for the document.
        3. Group chunks into batches of BATCH_SIZE.
        4. For each batch, call Gemini to generate questions.
        5. Parse, validate, and store quiz questions.
        6. Return statistics.

    Args:
        db: Database session.
        user_id: Owning user's UUID.
        document_id: Target document's UUID.
        question_count: Target number of questions per batch.

    Returns:
        Dict with message, quiz_id, total_questions, discarded_count.
    """
    doc = _get_document_or_404(db, document_id, user_id)

    if doc.status not in (DocumentStatus.READY,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot generate quiz: document status is '{doc.status.value}'. "
                "Document must be PROCESSED."
            ),
        )

    # Load all chunks
    chunks: list[Chunk] = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .all()
    )

    if not chunks:
        return {
            "message": "No chunks found for this document. No quiz generated.",
            "quiz_id": None,
            "total_questions": 0,
            "discarded_count": 0,
        }

    # Limit question count
    question_count = min(question_count, _MAX_PER_BATCH)

    # Batch chunks
    batches = batch_chunks(chunks)

    all_valid_questions: list[dict[str, Any]] = []
    total_generated = 0
    total_discarded = 0

    logger.info(
        "Quiz generation start",
        extra={
            "document_id": str(document_id),
            "user_id": str(user_id),
            "chunk_count": len(chunks),
            "batch_count": len(batches),
        },
    )

    # Call Gemini for each batch
    for batch_idx, batch in enumerate(batches):
        combined_text = "\n\n".join(
            f"[Chunk {c.chunk_index}] {c.content}" for c in batch
        )

        prompt = format_quiz_prompt(combined_text, question_count=question_count)
        start_time = time.monotonic()

        try:
            response = gemini_generate(
                prompt=prompt,
                system_instruction=QUIZ_SYSTEM_INSTRUCTION,
                model_name=_QUIZ_MODEL,
                timeout_seconds=_QUIZ_TIMEOUT,
            )
            raw_text = response["text"]
        except Exception as exc:
            logger.error(
                "Gemini call failed for batch %d/%d",
                batch_idx + 1,
                len(batches),
                extra={
                    "error": str(exc),
                    "document_id": str(document_id),
                    "batch_index": batch_idx,
                },
            )
            continue

        gemini_latency = time.monotonic() - start_time

        # Parse response
        raw_questions = parse_quiz_json(raw_text)

        if not raw_questions:
            logger.info(
                "No questions parsed from batch %d/%d",
                batch_idx + 1,
                len(batches),
                extra={
                    "document_id": str(document_id),
                    "gemini_latency_s": round(gemini_latency, 2),
                },
            )
            continue

        # Validate each question
        batch_generated = len(raw_questions)
        batch_discarded = 0
        batch_valid = 0

        for q_dict in raw_questions:
            validated = validate_question(q_dict)
            if validated is None:
                batch_discarded += 1
                continue
            validated["source_chunk_id"] = batch[0].id
            all_valid_questions.append(validated)
            batch_valid += 1

        total_generated += batch_generated
        total_discarded += batch_discarded

        logger.info(
            "Batch %d/%d done",
            batch_idx + 1,
            len(batches),
            extra={
                "document_id": str(document_id),
                "generated": batch_generated,
                "valid": batch_valid,
                "discarded": batch_discarded,
                "gemini_latency_s": round(gemini_latency, 2),
            },
        )

        # Enforce total max
        if len(all_valid_questions) >= settings.QUIZ_MAX_QUESTIONS:
            logger.info(
                "Reached max questions (%d), stopping early",
                settings.QUIZ_MAX_QUESTIONS,
            )
            break

    if not all_valid_questions:
        return {
            "message": "No valid questions could be generated from this document.",
            "quiz_id": None,
            "total_questions": 0,
            "discarded_count": total_discarded,
        }

    # Create Quiz record
    quiz = Quiz(
        user_id=user_id,
        document_id=document_id,
        title=f"Quiz on {doc.filename}",
        total_questions=len(all_valid_questions),
    )
    db.add(quiz)
    db.flush()

    # Create QuizQuestion records
    for idx, vq in enumerate(all_valid_questions):
        options_json = json.dumps(vq["options"]) if vq["options"] else None
        question = QuizQuestion(
            quiz_id=quiz.id,
            source_chunk_id=vq.get("source_chunk_id"),
            question_type=vq["type"],
            question_text=vq["question"],
            options=options_json,
            correct_answer=vq["correct_answer"],
            explanation=vq["explanation"],
            order_index=idx,
            difficulty="medium",
        )
        db.add(question)

    db.commit()
    db.refresh(quiz)

    # Invalidate search cache
    invalidate_search_cache(user_id)

    logger.info(
        "Quiz generation finish",
        extra={
            "quiz_id": str(quiz.id),
            "document_id": str(document_id),
            "user_id": str(user_id),
            "total_questions": quiz.total_questions,
            "total_discarded": total_discarded,
        },
    )

    return {
        "message": (
            f"Generated {quiz.total_questions} questions "
            f"({total_discarded} discarded from {total_generated} raw)"
        ),
        "quiz_id": quiz.id,
        "total_questions": quiz.total_questions,
        "discarded_count": total_discarded,
    }


# ---------------------------------------------------------------------------
# Quiz CRUD
# ---------------------------------------------------------------------------


def list_quizzes(
    db: Session,
    user_id: uuid.UUID,
    *,
    document_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List quizzes for a user, optionally filtered by document.

    Returns a paginated response.
    """
    query = db.query(Quiz).filter(
        Quiz.user_id == user_id,
        Quiz.deleted_at.is_(None),
    )

    if document_id is not None:
        query = query.filter(Quiz.document_id == document_id)

    total = query.count()
    query = query.order_by(Quiz.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    quizzes = query.all()

    return {
        "quizzes": quizzes,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


def get_quiz(db: Session, user_id: uuid.UUID, quiz_id: uuid.UUID) -> Quiz:
    """Get a quiz with all its questions. Ownership required."""
    quiz = _get_quiz_or_404(db, quiz_id, user_id)
    # Eagerly load questions
    quiz.questions  # noqa: B018 -- triggers lazy load
    return quiz


def delete_quiz(db: Session, user_id: uuid.UUID, quiz_id: uuid.UUID) -> None:
    """Soft-delete a quiz. Ownership required."""
    quiz = _get_quiz_or_404(db, quiz_id, user_id)
    quiz.deleted_at = datetime.now(timezone.utc)
    db.commit()


def delete_document_quizzes(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> int:
    """Soft-delete all quizzes belonging to a document. Ownership required."""
    doc = _get_document_or_404(db, document_id, user_id)
    now = datetime.now(timezone.utc)
    count = (
        db.query(Quiz)
        .filter(
            Quiz.document_id == document_id,
            Quiz.user_id == user_id,
            Quiz.deleted_at.is_(None),
        )
        .update({"deleted_at": now})
    )
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Attempt management (Phase 7 -- Scoring)
# ---------------------------------------------------------------------------


def calculate_score(correct: int, total: int) -> int:
    """Calculate percentage score from correct and total counts.

    Returns 0 if total is 0, otherwise int percentage.
    """
    if total <= 0:
        return 0
    return int(round((correct / total) * 100))


def submit_attempt(
    db: Session,
    user_id: uuid.UUID,
    quiz_id: uuid.UUID,
    *,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Submit an attempt for a quiz.

    Validates ownership, grades each answer, creates a QuizAttempt record,
    and returns the graded results.

    Args:
        db: Database session.
        user_id: Attempting user's UUID.
        quiz_id: Target quiz's UUID.
        answers: List of dicts with 'question_id' and 'answer' keys.
    """
    quiz = _get_quiz_or_404(db, quiz_id, user_id)

    # Load questions
    questions: list[QuizQuestion] = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.order_index)
        .all()
    )

    if not questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz has no questions",
        )

    # Build a lookup from question id to question
    q_lookup: dict[str, QuizQuestion] = {str(q.id): q for q in questions}

    # Grade each answer
    results = []
    correct_count = 0

    for ans in answers:
        qid = str(ans.get("question_id", ""))
        user_answer = str(ans.get("answer", "")).strip()

        question = q_lookup.get(qid)
        if question is None:
            continue

        # Check correctness
        is_correct = _is_answer_correct(user_answer, question.correct_answer, question.question_type)
        if is_correct:
            correct_count += 1

        results.append({
            "question_text": question.question_text,
            "user_answer": user_answer,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
            "is_correct": is_correct,
        })

    total = len(questions)
    score = calculate_score(correct_count, total)

    # Create attempt record
    attempt = QuizAttempt(
        quiz_id=quiz_id,
        user_id=user_id,
        score=score,
        total_questions=total,
        correct_answers=correct_count,
        answers=json.dumps(answers),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    logger.info(
        "Quiz attempt submitted",
        extra={
            "quiz_id": str(quiz_id),
            "user_id": str(user_id),
            "score": score,
            "correct": correct_count,
            "total": total,
            "attempt_id": str(attempt.id),
        },
    )

    return {
        "id": attempt.id,
        "quiz_id": quiz_id,
        "score": score,
        "total_questions": total,
        "correct_answers": correct_count,
        "completed_at": attempt.completed_at,
        "created_at": attempt.created_at,
        "results": results,
    }


def _is_answer_correct(user_answer: str, correct_answer: str, question_type: str) -> bool:
    """Compare user answer to correct answer with type-aware normalization.

    For true_false: case-insensitive comparison.
    For multiple_choice: single-letter comparison (case-insensitive).
    For short_answer: case-insensitive trimmed comparison.
    """
    ua = user_answer.strip().lower()
    ca = correct_answer.strip().lower()

    if question_type == "true_false":
        return ua == ca
    elif question_type == "multiple_choice":
        # Accept either "A" or "A. Option text" or just "a"
        ua_letter = ua[0] if ua else ""
        ca_letter = ca[0] if ca else ""
        return ua_letter == ca_letter or ua == ca
    else:
        # short_answer: exact match or containment
        return ua == ca or ca in ua or ua in ca


def list_attempts(
    db: Session,
    user_id: uuid.UUID,
    quiz_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List all attempts for a quiz. Ownership required.

    First verifies the quiz belongs to the user, then lists attempts.
    """
    _get_quiz_or_404(db, quiz_id, user_id)

    query = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == user_id,
        )
    )

    total = query.count()
    query = query.order_by(QuizAttempt.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    attempts = query.all()

    return {
        "attempts": attempts,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


def get_attempt(
    db: Session,
    user_id: uuid.UUID,
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
) -> dict[str, Any]:
    """Get a specific attempt with its graded results. Ownership required.

    Reconstructs results from the stored answers and quiz questions.
    """
    _get_quiz_or_404(db, quiz_id, user_id)

    attempt = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.id == attempt_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == user_id,
        )
        .first()
    )
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found",
        )

    # Load questions for result reconstruction
    questions: list[QuizQuestion] = (
        db.query(QuizQuestion)
        .filter(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.order_index)
        .all()
    )
    q_lookup: dict[str, QuizQuestion] = {str(q.id): q for q in questions}

    # Parse stored answers
    try:
        stored_answers: list[dict[str, Any]] = json.loads(attempt.answers or "[]")
    except (json.JSONDecodeError, TypeError):
        stored_answers = []

    # Reconstruct results
    results = []
    for ans in stored_answers:
        qid = str(ans.get("question_id", ""))
        user_answer = str(ans.get("answer", "")).strip()
        question = q_lookup.get(qid)
        if question is None:
            continue
        is_correct = _is_answer_correct(user_answer, question.correct_answer, question.question_type)
        results.append({
            "question_text": question.question_text,
            "user_answer": user_answer,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
            "is_correct": is_correct,
        })

    return {
        "id": attempt.id,
        "quiz_id": attempt.quiz_id,
        "score": attempt.score,
        "total_questions": attempt.total_questions,
        "correct_answers": attempt.correct_answers,
        "completed_at": attempt.completed_at,
        "created_at": attempt.created_at,
        "results": results,
    }
