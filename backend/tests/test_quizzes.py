"""
Tests for the Quiz Generator (Part 13).

Covers:
  - Parser: code fence removal, markdown stripping, malformed JSON
  - Validation: MCQ, true_false, short_answer, blank rejection
  - Batching: chunk grouping
  - Service: generation flow, empty documents, Gemini failure
  - API: generate, list, get, delete, attempt, review
  - Security: authentication, ownership, cross-user isolation
  - Scoring: percentage calculation, type-aware comparison
  - Pagination: list pagination
  - Cache: invalidation on generate/delete
"""
import json
import uuid
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_question import QuizQuestion


# ======================================================================
# Helper factories
# ======================================================================


def _create_document(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: DocumentStatus = DocumentStatus.READY,
) -> Document:
    doc = Document(
        user_id=user_id,
        filename="test.pdf",
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size=1024,
        storage_key=f"{user_id}/{uuid.uuid4()}/test.pdf",
        status=status,
        extension=".pdf",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _create_chunk(
    db: Session,
    document_id: uuid.UUID,
    *,
    chunk_index: int = 0,
    content: str = "Test chunk content for quiz generation.",
) -> Chunk:
    chunk = Chunk(
        document_id=document_id,
        chunk_index=chunk_index,
        content=content,
        source_type="pdf",
        character_start=0,
        character_end=len(content),
        token_estimate=50,
    )
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    return chunk


def _create_quiz(
    db: Session,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    title: str = "Test Quiz",
    total_questions: int = 3,
) -> Quiz:
    quiz = Quiz(
        user_id=user_id,
        document_id=document_id,
        title=title,
        total_questions=total_questions,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return quiz


def _create_question(
    db: Session,
    quiz_id: uuid.UUID,
    *,
    order_index: int = 0,
    question_type: str = "multiple_choice",
    question_text: str = "What is 2+2?",
    options: str | None = '["A. 3", "B. 4", "C. 5", "D. 6"]',
    correct_answer: str = "B",
    explanation: str = "2+2 equals 4",
) -> QuizQuestion:
    q = QuizQuestion(
        quiz_id=quiz_id,
        question_type=question_type,
        question_text=question_text,
        options=options,
        correct_answer=correct_answer,
        explanation=explanation,
        order_index=order_index,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


# ======================================================================
# Parser tests
# ======================================================================


class TestParser:
    """Unit tests for clean_gemini_response and parse_quiz_json."""

    def test_plain_json(self):
        from app.services.quiz_service import parse_quiz_json
        text = '[{"type": "multiple_choice", "question": "Q?", "correct_answer": "A", "explanation": "E"}]'
        result = parse_quiz_json(text)
        assert len(result) == 1
        assert result[0]["type"] == "multiple_choice"

    def test_code_fences_json(self):
        from app.services.quiz_service import parse_quiz_json
        text = '```json\n[{"type": "multiple_choice", "question": "Q?", "correct_answer": "A", "explanation": "E"}]\n```'
        result = parse_quiz_json(text)
        assert len(result) == 1

    def test_code_fences_plain(self):
        from app.services.quiz_service import parse_quiz_json
        text = '```\n[{"type": "multiple_choice", "question": "Q?", "correct_answer": "A", "explanation": "E"}]\n```'
        result = parse_quiz_json(text)
        assert len(result) == 1

    def test_trailing_text_after_json(self):
        from app.services.quiz_service import parse_quiz_json
        text = '[{"type": "multiple_choice", "question": "Q?", "correct_answer": "A", "explanation": "E"}]\n\nThis quiz covers key concepts...'
        result = parse_quiz_json(text)
        assert len(result) == 1

    def test_leading_text_before_json(self):
        from app.services.quiz_service import parse_quiz_json
        text = 'Here are some questions:\n[{"type": "multiple_choice", "question": "Q?", "correct_answer": "A", "explanation": "E"}]'
        result = parse_quiz_json(text)
        assert len(result) == 1

    def test_malformed_json(self):
        from app.services.quiz_service import parse_quiz_json
        result = parse_quiz_json("not json at all")
        assert result == []

    def test_empty_string(self):
        from app.services.quiz_service import parse_quiz_json
        result = parse_quiz_json("")
        assert result == []

    def test_single_object_wrapped(self):
        from app.services.quiz_service import parse_quiz_json
        text = '{"type": "multiple_choice", "question": "Q?", "correct_answer": "A", "explanation": "E"}'
        result = parse_quiz_json(text)
        assert len(result) == 1

    def test_code_fence_with_trailing_text(self):
        from app.services.quiz_service import parse_quiz_json
        text = '```json\n[{"type": "mcq", "question": "Q?", "correct_answer": "A", "explanation": "E"}]\n```\nHope this helps!'
        result = parse_quiz_json(text)
        assert len(result) == 1

    def test_empty_json_array(self):
        from app.services.quiz_service import parse_quiz_json
        result = parse_quiz_json("[]")
        assert result == []


# ======================================================================
# Validation tests
# ======================================================================


class TestValidation:
    """Unit tests for validate_question."""

    def test_valid_mcq(self):
        from app.services.quiz_service import validate_question
        q = {"type": "multiple_choice", "question": "What is 2+2?", "options": ["A. 3", "B. 4", "C. 5", "D. 6"], "correct_answer": "B", "explanation": "2+2 equals 4"}
        result = validate_question(q)
        assert result is not None
        assert result["type"] == "multiple_choice"

    def test_valid_true_false(self):
        from app.services.quiz_service import validate_question
        q = {"type": "true_false", "question": "The sky is blue.", "correct_answer": "True", "explanation": "The sky appears blue due to Rayleigh scattering."}
        result = validate_question(q)
        assert result is not None
        assert result["type"] == "true_false"
        assert result["options"] is None

    def test_valid_short_answer(self):
        from app.services.quiz_service import validate_question
        q = {"type": "short_answer", "question": "What is the capital of France?", "correct_answer": "Paris", "explanation": "Paris is the capital of France."}
        result = validate_question(q)
        assert result is not None
        assert result["type"] == "short_answer"
        assert result["options"] is None

    def test_invalid_type(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "essay", "question": "Write.", "correct_answer": "N/A", "explanation": "N/A"}) is None

    def test_empty_question(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "multiple_choice", "question": "", "options": ["A", "B", "C", "D"], "correct_answer": "A", "explanation": "Test"}) is None

    def test_empty_correct_answer(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "true_false", "question": "Is this true?", "correct_answer": "", "explanation": "Test"}) is None

    def test_empty_explanation(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "short_answer", "question": "What?", "correct_answer": "Answer", "explanation": ""}) is None

    def test_mcq_less_than_4_options(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "multiple_choice", "question": "Q?", "options": ["A", "B"], "correct_answer": "A", "explanation": "Test"}) is None

    def test_mcq_more_than_4_options(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "multiple_choice", "question": "Q?", "options": ["A", "B", "C", "D", "E"], "correct_answer": "A", "explanation": "Test"}) is None

    def test_mcq_non_list_options(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "multiple_choice", "question": "Q?", "options": "A, B, C, D", "correct_answer": "A", "explanation": "Test"}) is None

    def test_mcq_empty_option_string(self):
        from app.services.quiz_service import validate_question
        assert validate_question({"type": "multiple_choice", "question": "Q?", "options": ["A", "B", "", "D"], "correct_answer": "A", "explanation": "Test"}) is None


# ======================================================================
# Batching tests
# ======================================================================


class TestBatching:
    """Unit tests for batch_chunks."""

    def test_empty_chunks(self):
        from app.services.quiz_service import batch_chunks
        from app.models.chunk import Chunk
        assert batch_chunks([]) == []

    def test_single_batch(self):
        from app.services.quiz_service import batch_chunks
        from app.models.chunk import Chunk
        chunks = [Chunk(id=uuid.uuid4()) for _ in range(3)]
        batches = batch_chunks(chunks, batch_size=5)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_multiple_batches(self):
        from app.services.quiz_service import batch_chunks
        from app.models.chunk import Chunk
        chunks = [Chunk(id=uuid.uuid4()) for _ in range(12)]
        batches = batch_chunks(chunks, batch_size=5)
        assert len(batches) == 3
        assert len(batches[0]) == 5
        assert len(batches[1]) == 5
        assert len(batches[2]) == 2

    def test_exact_batch(self):
        from app.services.quiz_service import batch_chunks
        from app.models.chunk import Chunk
        chunks = [Chunk(id=uuid.uuid4()) for _ in range(10)]
        batches = batch_chunks(chunks, batch_size=5)
        assert len(batches) == 2
        assert len(batches[0]) == 5
        assert len(batches[1]) == 5


# ======================================================================
# Scoring tests
# ======================================================================


class TestScoring:
    """Unit tests for calculate_score and _is_answer_correct."""

    def test_perfect_score(self):
        from app.services.quiz_service import calculate_score
        assert calculate_score(5, 5) == 100

    def test_half_score(self):
        from app.services.quiz_service import calculate_score
        assert calculate_score(3, 6) == 50

    def test_zero_correct(self):
        from app.services.quiz_service import calculate_score
        assert calculate_score(0, 5) == 0

    def test_zero_total(self):
        from app.services.quiz_service import calculate_score
        assert calculate_score(0, 0) == 0

    def test_rounding(self):
        from app.services.quiz_service import calculate_score
        assert calculate_score(1, 3) == 33


class TestAnswerComparison:
    """Unit tests for _is_answer_correct."""

    def test_mcq_correct(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("B", "B", "multiple_choice") is True

    def test_mcq_incorrect(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("A", "B", "multiple_choice") is False

    def test_mcq_case_insensitive(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("b", "B", "multiple_choice") is True

    def test_true_false_exact(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("True", "True", "true_false") is True

    def test_true_false_case_insensitive(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("true", "True", "true_false") is True

    def test_short_answer_exact(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("Paris", "Paris", "short_answer") is True

    def test_short_answer_case_insensitive(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("paris", "Paris", "short_answer") is True

    def test_short_answer_containment(self):
        from app.services.quiz_service import _is_answer_correct
        assert _is_answer_correct("Paris is the capital", "Paris", "short_answer") is True


# ======================================================================
# Generation error/edge-case tests (unit, no Gemini)
# ======================================================================


class TestGenerateService:
    """Tests for generate_quiz edge cases."""

    def test_document_not_found(self, db_session, user):
        from app.services.quiz_service import generate_quiz
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            generate_quiz(db_session, user.id, uuid.uuid4())
        assert exc.value.status_code == 404

    def test_document_not_processed(self, db_session, user):
        doc = _create_document(db_session, user.id, status=DocumentStatus.UPLOADED)
        from app.services.quiz_service import generate_quiz
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            generate_quiz(db_session, user.id, doc.id)
        assert exc.value.status_code == 400

    def test_no_chunks(self, db_session, user):
        doc = _create_document(db_session, user.id)
        from app.services.quiz_service import generate_quiz
        result = generate_quiz(db_session, user.id, doc.id)
        assert result["total_questions"] == 0
        assert result["quiz_id"] is None

    def test_gemini_call_failure(self, db_session, user):
        doc = _create_document(db_session, user.id)
        _create_chunk(db_session, doc.id)
        from app.services.quiz_service import generate_quiz
        from app.services.llm_service import LLMError
        with patch("app.services.quiz_service.gemini_generate") as mock:
            mock.side_effect = LLMError("API error")
            result = generate_quiz(db_session, user.id, doc.id)
            assert result["total_questions"] == 0
            assert result["quiz_id"] is None

    def test_gemini_empty_response(self, db_session, user):
        doc = _create_document(db_session, user.id)
        _create_chunk(db_session, doc.id)
        from app.services.quiz_service import generate_quiz
        with patch("app.services.quiz_service.gemini_generate") as mock:
            mock.return_value = {"text": "", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "latency_ms": 100}
            result = generate_quiz(db_session, user.id, doc.id)
            assert result["total_questions"] == 0

    def test_gemini_invalid_json(self, db_session, user):
        doc = _create_document(db_session, user.id)
        _create_chunk(db_session, doc.id)
        from app.services.quiz_service import generate_quiz
        with patch("app.services.quiz_service.gemini_generate") as mock:
            mock.return_value = {"text": "not valid json at all", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "latency_ms": 100}
            result = generate_quiz(db_session, user.id, doc.id)
            assert result["total_questions"] == 0


# ======================================================================
# API tests (integration via TestClient)
# ======================================================================


class TestAPI:
    """Full integration tests through the API, using api_user so that
    DB-created data matches the auth_headers user."""

    def test_generate_quiz_success(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        _create_chunk(db_session, doc.id)
        _create_chunk(db_session, doc.id, chunk_index=1)

        valid_json = json.dumps([
            {"type": "multiple_choice", "question": "Q1?", "options": ["A. a", "B. b", "C. c", "D. d"], "correct_answer": "A", "explanation": "E1"},
            {"type": "true_false", "question": "Q2?", "correct_answer": "True", "explanation": "E2"},
        ])

        with patch("app.services.quiz_service.gemini_generate") as mock:
            mock.return_value = {"text": valid_json, "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "latency_ms": 500}
            response = client.post(
                f"/api/v1/documents/{doc.id}/quizzes/generate?question_count=3",
                headers=auth_headers,
            )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["total_questions"] == 2
        assert data["quiz_id"] is not None
        assert data["discarded_count"] == 0

    def test_generate_quiz_discards_invalid(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        _create_chunk(db_session, doc.id)

        raw = json.dumps([
            {"type": "multiple_choice", "question": "Q1?", "options": ["A", "B", "C", "D"], "correct_answer": "A", "explanation": "E1"},
            {"type": "multiple_choice", "question": "", "options": ["A", "B"], "correct_answer": "A", "explanation": "E2"},
        ])

        with patch("app.services.quiz_service.gemini_generate") as mock:
            mock.return_value = {"text": raw, "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "latency_ms": 500}
            response = client.post(
                f"/api/v1/documents/{doc.id}/quizzes/generate",
                headers=auth_headers,
            )
        assert response.status_code == 201
        data = response.json()
        assert data["total_questions"] == 1
        assert data["discarded_count"] == 1

    def test_generate_quiz_no_auth(self, client, db_session):
        doc = _create_document(db_session, uuid.uuid4())
        response = client.post(f"/api/v1/documents/{doc.id}/quizzes/generate")
        assert response.status_code == 401

    def test_generate_quiz_wrong_user(self, client, auth_headers, db_session):
        other_user_id = uuid.uuid4()
        doc = _create_document(db_session, other_user_id)
        response = client.post(
            f"/api/v1/documents/{doc.id}/quizzes/generate",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_generate_quiz_no_chunks(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        response = client.post(
            f"/api/v1/documents/{doc.id}/quizzes/generate",
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["total_questions"] == 0

    def test_list_quizzes_empty(self, client, auth_headers):
        response = client.get("/api/v1/quizzes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["quizzes"] == []

    def test_list_quizzes_with_data(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        _create_quiz(db_session, api_user.id, doc.id)

        response = client.get("/api/v1/quizzes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["quizzes"]) == 1
        assert data["quizzes"][0]["id"] is not None

    def test_list_quizzes_filter_by_document(self, client, auth_headers, db_session, api_user):
        doc1 = _create_document(db_session, api_user.id)
        doc2 = _create_document(db_session, api_user.id)
        _create_quiz(db_session, api_user.id, doc1.id)
        _create_quiz(db_session, api_user.id, doc2.id)

        response = client.get(f"/api/v1/quizzes?document_id={doc1.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_get_quiz_success(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=2)
        _create_question(db_session, quiz.id, order_index=0)
        _create_question(db_session, quiz.id, order_index=1, question_type="true_false", question_text="Is 1+1=2?", options=None, correct_answer="True", explanation="Basic math")

        response = client.get(f"/api/v1/quizzes/{quiz.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Quiz"
        assert len(data["questions"]) == 2

    def test_get_quiz_not_found(self, client, auth_headers):
        response = client.get(f"/api/v1/quizzes/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404

    def test_get_quiz_cross_user(self, client, auth_headers, db_session):
        other_user_id = uuid.uuid4()
        doc = _create_document(db_session, other_user_id)
        quiz = _create_quiz(db_session, other_user_id, doc.id)
        response = client.get(f"/api/v1/quizzes/{quiz.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_quiz(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id)

        response = client.delete(f"/api/v1/quizzes/{quiz.id}", headers=auth_headers)
        assert response.status_code == 204

        db_session.refresh(quiz)
        assert quiz.deleted_at is not None

    def test_delete_quiz_not_found(self, client, auth_headers):
        # FastAPI's HTTPException 404 is returned as JSON, not 204
        response = client.delete(f"/api/v1/quizzes/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_document_quizzes(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        _create_quiz(db_session, api_user.id, doc.id)
        _create_quiz(db_session, api_user.id, doc.id)

        response = client.delete(f"/api/v1/documents/{doc.id}/quizzes", headers=auth_headers)
        assert response.status_code == 204

        remaining = db_session.query(Quiz).filter(Quiz.document_id == doc.id, Quiz.deleted_at.is_(None)).count()
        assert remaining == 0

    def test_generate_quiz_unprocessed_document(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id, status=DocumentStatus.UPLOADED)
        response = client.post(
            f"/api/v1/documents/{doc.id}/quizzes/generate",
            headers=auth_headers,
        )
        assert response.status_code == 400


# ======================================================================
# Attempt tests
# ======================================================================


class TestAttempt:
    """Tests for quiz attempt submission, scoring, and review."""

    def test_submit_attempt_success(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=2)
        q1 = _create_question(db_session, quiz.id, order_index=0, question_text="Q?", correct_answer="B")
        q2 = _create_question(db_session, quiz.id, order_index=1, question_type="true_false", question_text="Sky is blue?", options=None, correct_answer="True", explanation="Physics")

        payload = [{"question_id": str(q1.id), "answer": "B"}, {"question_id": str(q2.id), "answer": "True"}]

        response = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["score"] == 100
        assert data["correct_answers"] == 2
        assert data["total_questions"] == 2
        assert len(data["results"]) == 2

    def test_submit_attempt_partial_score(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=2)
        q1 = _create_question(db_session, quiz.id, order_index=0)
        q2 = _create_question(db_session, quiz.id, order_index=1, question_type="true_false", question_text="Sky is blue?", options=None, correct_answer="True", explanation="Physics")

        payload = [{"question_id": str(q1.id), "answer": "A"}, {"question_id": str(q2.id), "answer": "True"}]

        response = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["score"] == 50
        assert data["correct_answers"] == 1

    def test_submit_attempt_no_auth(self, client, db_session, api_user):
        quiz = _create_quiz(db_session, api_user.id, uuid.uuid4())
        response = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", json=[{"question_id": str(uuid.uuid4()), "answer": "B"}])
        assert response.status_code == 401

    def test_submit_attempt_cross_user(self, client, auth_headers, db_session):
        other = uuid.uuid4()
        doc = _create_document(db_session, other)
        quiz = _create_quiz(db_session, other, doc.id)
        response = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=[{"question_id": str(uuid.uuid4()), "answer": "B"}])
        assert response.status_code == 404

    def test_submit_attempt_empty_quiz(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=0)
        response = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=[])
        assert response.status_code == 400

    def test_list_attempts(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id)
        q1 = _create_question(db_session, quiz.id, order_index=0)

        payload = [{"question_id": str(q1.id), "answer": "B"}]
        client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=payload)

        response = client.get(f"/api/v1/quizzes/{quiz.id}/attempts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["attempts"]) == 1

    def test_list_attempts_empty(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id)

        response = client.get(f"/api/v1/quizzes/{quiz.id}/attempts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_get_attempt_detail(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=1)
        q1 = _create_question(db_session, quiz.id, order_index=0)

        payload = [{"question_id": str(q1.id), "answer": "B"}]
        submit_resp = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=payload)
        attempt_id = submit_resp.json()["id"]

        response = client.get(f"/api/v1/quizzes/{quiz.id}/attempts/{attempt_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["score"] == 100
        assert len(data["results"]) == 1
        assert data["results"][0]["is_correct"] is True
        assert data["results"][0]["correct_answer"] == "B"

    def test_get_attempt_not_found(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id)
        response = client.get(f"/api/v1/quizzes/{quiz.id}/attempts/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404

    def test_attempt_review_mode(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=1)
        q1 = _create_question(db_session, quiz.id, order_index=0, question_text="Capital of France?", correct_answer="Paris", explanation="Paris is the capital")

        payload = [{"question_id": str(q1.id), "answer": "London"}]
        submit_resp = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=payload)
        attempt_id = submit_resp.json()["id"]

        response = client.get(f"/api/v1/quizzes/{quiz.id}/attempts/{attempt_id}", headers=auth_headers)
        data = response.json()
        result = data["results"][0]
        assert result["user_answer"] == "London"
        assert result["correct_answer"] == "Paris"
        assert result["is_correct"] is False
        assert result["explanation"] == "Paris is the capital"

    def test_multiple_attempts_same_quiz(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=1)
        q1 = _create_question(db_session, quiz.id, order_index=0)

        p1 = [{"question_id": str(q1.id), "answer": "B"}]
        p2 = [{"question_id": str(q1.id), "answer": "A"}]

        r1 = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=p1)
        r2 = client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=p2)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["score"] == 100
        assert r2.json()["score"] == 0


# ======================================================================
# Pagination tests
# ======================================================================


class TestPagination:
    """Tests for paginated endpoints."""

    def test_quiz_list_pagination(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        for _ in range(5):
            _create_quiz(db_session, api_user.id, doc.id)

        r1 = client.get("/api/v1/quizzes?page=1&page_size=2", headers=auth_headers)
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["quizzes"]) == 2
        assert d1["has_next"] is True
        assert d1["total"] == 5

        r3 = client.get("/api/v1/quizzes?page=3&page_size=2", headers=auth_headers)
        assert r3.status_code == 200
        d3 = r3.json()
        assert len(d3["quizzes"]) == 1
        assert d3["has_next"] is False

    def test_attempt_list_pagination(self, client, auth_headers, db_session, api_user):
        doc = _create_document(db_session, api_user.id)
        quiz = _create_quiz(db_session, api_user.id, doc.id, total_questions=1)
        q1 = _create_question(db_session, quiz.id, order_index=0)

        payload = [{"question_id": str(q1.id), "answer": "B"}]
        for _ in range(4):
            client.post(f"/api/v1/quizzes/{quiz.id}/attempt", headers=auth_headers, json=payload)

        r = client.get(f"/api/v1/quizzes/{quiz.id}/attempts?page=1&page_size=2", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert len(d["attempts"]) == 2
        assert d["has_next"] is True
        assert d["total"] == 4


# ======================================================================
# Security tests
# ======================================================================


class TestSecurity:
    """Tests for auth and ownership enforcement."""

    def test_no_auth_token(self, client):
        endpoints = [
            ("GET", "/api/v1/quizzes"),
            ("GET", f"/api/v1/quizzes/{uuid.uuid4()}"),
            ("DELETE", f"/api/v1/quizzes/{uuid.uuid4()}"),
            ("POST", f"/api/v1/documents/{uuid.uuid4()}/quizzes/generate"),
        ]
        for method, url in endpoints:
            response = getattr(client, method.lower())(url)
            assert response.status_code == 401, f"{method} {url} should be 401"

    def test_cross_user_quiz_isolation(self, client, auth_headers, db_session):
        """Create a second user in the same DB and verify isolation."""
        from app.models.user import User
        from app.core.security import hash_password

        other = User(email="other_quiz@test.com", full_name="Other", hashed_password=hash_password("Pass1234"))
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        doc = _create_document(db_session, other.id)
        quiz = _create_quiz(db_session, other.id, doc.id)

        r = client.get(f"/api/v1/quizzes/{quiz.id}", headers=auth_headers)
        assert r.status_code == 404

    def test_cross_user_attempt_isolation(self, client, auth_headers, db_session):
        """Create a second user in the same DB and verify attempt isolation."""
        from app.models.user import User
        from app.core.security import hash_password

        other = User(email="other_attempt@test.com", full_name="Other", hashed_password=hash_password("Pass1234"))
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        doc = _create_document(db_session, other.id)
        quiz = _create_quiz(db_session, other.id, doc.id)

        r = client.get(f"/api/v1/quizzes/{quiz.id}/attempts", headers=auth_headers)
        assert r.status_code == 404

    def test_quiz_generate_cross_document(self, client, auth_headers, db_session):
        other = uuid.uuid4()
        doc = _create_document(db_session, other)
        r = client.post(f"/api/v1/documents/{doc.id}/quizzes/generate", headers=auth_headers)
        assert r.status_code == 404


# ======================================================================
# Cache invalidation tests
# ======================================================================


class TestCache:
    """Tests for cache invalidation on quiz operations."""

    def test_invalidate_quiz_cache_exists(self):
        from app.services.cache_service import invalidate_quiz_cache
        uid = uuid.uuid4()
        invalidate_quiz_cache(uid)
        invalidate_quiz_cache(uid, quiz_id=uuid.uuid4())

    def test_cache_keys_format(self):
        from app.core.cache_keys import quiz_list_key, quiz_detail_key, quiz_attempt_list_key
        uid = uuid.uuid4()
        assert str(uid) in quiz_list_key(uid)
        assert "quizzes:" in quiz_list_key(uid)
        assert str(uid) in quiz_detail_key(uid)
        assert "quiz:" in quiz_detail_key(uid)
        assert "attempts:" in quiz_attempt_list_key(uid)
        assert str(uid) in quiz_attempt_list_key(uid)
