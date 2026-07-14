"""
Pydantic v2 schemas for the Quiz system (Part 13).

Follows the same patterns as flashcard.py — Pydantic v2 with
validation_alias for ORM→API field mapping.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

import json
from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Question-level schemas
# ──────────────────────────────────────────────


class QuizQuestionSchema(BaseModel):
    """Schema for a single quiz question returned in responses."""

    id: UUID
    question_type: str = Field(validation_alias="question_type")
    question_text: str = Field(validation_alias="question_text")
    options: list[str] | None = None
    correct_answer: str = Field(validation_alias="correct_answer")
    explanation: str | None = None
    order_index: int = Field(validation_alias="order_index")
    difficulty: str | None = "medium"
    source_chunk_id: UUID | None = Field(default=None, validation_alias="source_chunk_id")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("options", mode="before")
    @classmethod
    def _decode_options(cls, v: object) -> object:
        """Decode JSON-string options from the DB into a list.

        The model stores options as a JSON-encoded Text column.  When loading
        from the ORM the value is a string and needs to be parsed back into a
        list; when constructing from dict (e.g. unit tests) it's already a list.
        """
        if isinstance(v, str) and v:
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


class QuizQuestionPublic(BaseModel):
    """Schema for a quiz question WITHOUT the correct_answer (for quiz taking)."""

    id: UUID
    question_type: str = Field(validation_alias="question_type")
    question_text: str = Field(validation_alias="question_text")
    options: list[str] | None = None
    order_index: int = Field(validation_alias="order_index")
    difficulty: str | None = "medium"
    source_chunk_id: UUID | None = Field(default=None, validation_alias="source_chunk_id")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("options", mode="before")
    @classmethod
    def _decode_options(cls, v: object) -> object:
        if isinstance(v, str) and v:
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


# ──────────────────────────────────────────────
# Quiz-level schemas
# ──────────────────────────────────────────────


class QuizResponse(BaseModel):
    """Full quiz response with all questions."""

    id: UUID
    user_id: UUID = Field(validation_alias="user_id")
    document_id: UUID = Field(validation_alias="document_id")
    title: str
    total_questions: int = Field(validation_alias="total_questions")
    questions: list[QuizQuestionSchema] = []
    created_at: datetime = Field(validation_alias="created_at")
    updated_at: datetime = Field(validation_alias="updated_at")

    model_config = {"from_attributes": True, "populate_by_name": True}


class QuizListResponse(BaseModel):
    """Paginated list of quizzes (without questions)."""

    quizzes: list["QuizSummary"]
    total: int
    page: int
    page_size: int
    has_next: bool


class QuizSummary(BaseModel):
    """Lightweight quiz summary for list views."""

    id: UUID
    title: str
    document_id: UUID = Field(validation_alias="document_id")
    total_questions: int = Field(validation_alias="total_questions")
    created_at: datetime = Field(validation_alias="created_at")

    model_config = {"from_attributes": True, "populate_by_name": True}


class QuizGenerateResponse(BaseModel):
    """Response after quiz generation."""

    message: str
    quiz_id: UUID | None = None
    total_questions: int = 0
    discarded_count: int = 0


# ──────────────────────────────────────────────
# Attempt-level schemas
# ──────────────────────────────────────────────


class QuizAttemptCreate(BaseModel):
    """Request body for submitting a quiz attempt."""

    answers: list[dict[str, Any]]


class AttemptAnswerResult(BaseModel):
    """Result for a single answer in an attempt."""

    question_text: str = Field(validation_alias="question_text")
    user_answer: str
    correct_answer: str = Field(validation_alias="correct_answer")
    explanation: str | None = None
    is_correct: bool


class QuizAttemptResponse(BaseModel):
    """Response after submitting a quiz attempt."""

    id: UUID
    quiz_id: UUID = Field(validation_alias="quiz_id")
    score: int
    total_questions: int = Field(validation_alias="total_questions")
    correct_answers: int = Field(validation_alias="correct_answers")
    completed_at: datetime | None = Field(default=None, validation_alias="completed_at")
    created_at: datetime = Field(validation_alias="created_at")
    results: list[AttemptAnswerResult] = []

    model_config = {"from_attributes": True, "populate_by_name": True}


class QuizAttemptResult(BaseModel):
    """Detailed result of a completed attempt (for review mode)."""

    id: UUID
    quiz_id: UUID = Field(validation_alias="quiz_id")
    score: int
    total_questions: int = Field(validation_alias="total_questions")
    correct_answers: int = Field(validation_alias="correct_answers")
    completed_at: datetime | None = Field(default=None, validation_alias="completed_at")
    created_at: datetime = Field(validation_alias="created_at")
    results: list[AttemptAnswerResult] = []

    model_config = {"from_attributes": True, "populate_by_name": True}


class QuizAttemptListResponse(BaseModel):
    """Paginated list of attempts for a quiz."""

    attempts: list["AttemptSummary"]
    total: int
    page: int
    page_size: int
    has_next: bool


class AttemptSummary(BaseModel):
    """Lightweight attempt summary for list views."""

    id: UUID
    quiz_id: UUID = Field(validation_alias="quiz_id")
    score: int
    total_questions: int = Field(validation_alias="total_questions")
    correct_answers: int = Field(validation_alias="correct_answers")
    completed_at: datetime | None = Field(default=None, validation_alias="completed_at")
    created_at: datetime = Field(validation_alias="created_at")

    model_config = {"from_attributes": True, "populate_by_name": True}


# Update forward references
QuizListResponse.model_rebuild()
QuizAttemptListResponse.model_rebuild()
