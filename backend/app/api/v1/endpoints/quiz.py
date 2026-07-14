"""
Quiz API endpoints.

Pattern follows flashcards.py:
  - POST generate
  - GET list
  - GET detail
  - DELETE single
  - DELETE all for document
  - POST attempt
  - GET attempts list
  - GET attempt detail

Every endpoint enforces JWT auth and ownership.
"""
import uuid

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.quiz import (
    QuizAttemptListResponse,
    QuizAttemptResponse,
    QuizAttemptResult,
    QuizGenerateResponse,
    QuizListResponse,
    QuizResponse,
)
from app.services.quiz_service import (
    generate_quiz,
    list_quizzes,
    get_quiz,
    delete_quiz,
    delete_document_quizzes,
    submit_attempt,
    list_attempts,
    get_attempt,
)
from app.core.logging import get_logger

logger = get_logger("app.api.v1.endpoints.quiz")

router = APIRouter(tags=["Quizzes"])


@router.post(
    "/documents/{document_id}/quizzes/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=QuizGenerateResponse,
)
def api_generate_quiz(
    document_id: uuid.UUID,
    *,
    question_count: int = Query(default=5, ge=1, le=20, description="Target question count per batch"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate a quiz from a document's chunks."""
    result = generate_quiz(
        db,
        user_id=current_user.id,
        document_id=document_id,
        question_count=question_count,
    )
    return result


@router.get(
    "/quizzes",
    response_model=QuizListResponse,
)
def api_list_quizzes(
    document_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List quizzes for the current user, optionally filtered by document."""
    return list_quizzes(
        db,
        user_id=current_user.id,
        document_id=document_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/quizzes/{quiz_id}",
    response_model=QuizResponse,
)
def api_get_quiz(
    quiz_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a quiz with all its questions."""
    quiz = get_quiz(db, user_id=current_user.id, quiz_id=quiz_id)
    return quiz


@router.delete(
    "/quizzes/{quiz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def api_delete_quiz(
    quiz_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a quiz."""
    delete_quiz(db, user_id=current_user.id, quiz_id=quiz_id)


@router.delete(
    "/documents/{document_id}/quizzes",
    status_code=status.HTTP_204_NO_CONTENT,
)
def api_delete_document_quizzes(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete all quizzes for a document."""
    delete_document_quizzes(db, user_id=current_user.id, document_id=document_id)


@router.post(
    "/quizzes/{quiz_id}/attempt",
    status_code=status.HTTP_201_CREATED,
    response_model=QuizAttemptResponse,
)
def api_submit_attempt(
    quiz_id: uuid.UUID,
    answers: list[dict] = Body(..., description="List of {question_id, answer} objects"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit answers for a quiz attempt."""
    result = submit_attempt(
        db,
        user_id=current_user.id,
        quiz_id=quiz_id,
        answers=answers,
    )
    return result


@router.get(
    "/quizzes/{quiz_id}/attempts",
    response_model=QuizAttemptListResponse,
)
def api_list_attempts(
    quiz_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all attempts for a quiz."""
    return list_attempts(
        db,
        user_id=current_user.id,
        quiz_id=quiz_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/quizzes/{quiz_id}/attempts/{attempt_id}",
    response_model=QuizAttemptResult,
)
def api_get_attempt(
    quiz_id: uuid.UUID,
    attempt_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a specific attempt with graded results (review mode)."""
    return get_attempt(
        db,
        user_id=current_user.id,
        quiz_id=quiz_id,
        attempt_id=attempt_id,
    )
