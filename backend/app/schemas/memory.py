"""Pydantic schemas for the memory system."""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MemoryType(str, enum.Enum):
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    GOAL = "GOAL"


# ── Request Schemas ─────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    """Create a new memory manually."""
    type: MemoryType = Field(..., description="Memory type: FACT, PREFERENCE, or GOAL")
    content: str = Field(
        ..., min_length=1, max_length=2000,
        description="The memory content",
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Confidence score (0.0–1.0)",
    )

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped


class MemoryUpdate(BaseModel):
    """Update an existing memory."""
    content: Optional[str] = Field(
        None, min_length=1, max_length=2000,
        description="Updated memory content",
    )
    type: Optional[MemoryType] = Field(
        None, description="Updated memory type",
    )
    is_active: Optional[bool] = Field(
        None, description="Set inactive to exclude from prompts",
    )

    @field_validator("content")
    @classmethod
    def content_not_blank_if_set(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("content must not be blank")
            return stripped
        return v


# ── Response Schemas ────────────────────────────────────────────────

class MemoryResponse(BaseModel):
    """A single memory entry."""
    model_config = {"from_attributes": True}

    id: UUID
    type: MemoryType = Field(validation_alias="memory_type")
    content: str
    confidence: float
    is_active: bool
    source_message_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class MemoryListResponse(BaseModel):
    """Paginated list of memories."""
    memories: list[MemoryResponse]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False


class MemoryDeleteResponse(BaseModel):
    """Response after deleting memories."""
    detail: str
    deleted_count: int = 0
