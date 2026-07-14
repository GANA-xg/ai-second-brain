"""Pydantic schemas for the flashcard system."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.flashcard import FlashcardDifficulty


# ── Request Schemas ─────────────────────────────────────────────────


class FlashcardGenerateRequest(BaseModel):
    """Request to generate flashcards from a document."""
    model_config = {"extra": "forbid"}


class FlashcardUpdate(BaseModel):
    """Update an existing flashcard's front/back text."""
    front: Optional[str] = Field(
        None, min_length=1, max_length=5000,
        description="Updated front (question) text",
    )
    back: Optional[str] = Field(
        None, min_length=1, max_length=5000,
        description="Updated back (answer) text",
    )

    @field_validator("front", "back")
    @classmethod
    def not_blank_if_set(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Text must not be blank")
            return stripped
        return v


# ── Response Schemas ────────────────────────────────────────────────


class FlashcardResponse(BaseModel):
    """A single flashcard."""
    model_config = {"from_attributes": True}

    id: UUID
    user_id: UUID
    document_id: UUID
    source_chunk_id: Optional[UUID] = None
    front: str = Field(validation_alias="question")
    back: str = Field(validation_alias="answer")
    difficulty: FlashcardDifficulty
    created_at: datetime
    updated_at: datetime


class FlashcardListResponse(BaseModel):
    """Paginated list of flashcards."""
    flashcards: list[FlashcardResponse]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False


class FlashcardGenerateResponse(BaseModel):
    """Response after generating flashcards."""
    message: str
    generated_count: int
    discarded_count: int = 0
    total_count: int = 0


class FlashcardDeleteResponse(BaseModel):
    """Response after deleting flashcards."""
    detail: str
    deleted_count: int = 0
