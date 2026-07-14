"""Pydantic schemas for the RAG chat system and conversation management."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Citation ─────────────────────────────────────────────────────────

class Citation(BaseModel):
    """A citation linking an answer statement to a source document chunk."""

    document_id: UUID
    filename: str
    chunk_id: UUID
    page: Optional[int] = None
    score: float


# ── Chat Request / Response ──────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request to ask a question against the user's uploaded documents."""

    question: str = Field(..., min_length=1, max_length=4096, description="The user's question")
    conversation_id: Optional[UUID] = Field(
        None, description="Existing conversation ID or None to start a new conversation"
    )
    top_k: Optional[int] = Field(None, ge=1, le=50, description="Override default Top-K")
    score_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Override default score threshold")


class RetrievedChunk(BaseModel):
    """A single chunk returned from the vector search with metadata."""

    chunk_id: UUID
    document_id: UUID
    score: float
    content: str
    filename: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    source_type: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from the RAG pipeline."""

    answer: str
    citations: list[Citation]
    conversation_id: UUID
    message_id: UUID
    retrieved_chunks: list[RetrievedChunk]
    prompt_version: str
    model_used: str


class ChatErrorResponse(BaseModel):
    """Error response for RAG failures."""

    detail: str
    code: str


# ── Conversation Schemas ─────────────────────────────────────────────

class ConversationCreate(BaseModel):
    """Request to create a new conversation."""

    title: Optional[str] = Field(
        None, max_length=255, description="Optional title. Auto-generated from first message if omitted."
    )


class ConversationUpdate(BaseModel):
    """Request to update a conversation."""

    title: str = Field(..., min_length=1, max_length=255, description="New conversation title")


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""

    id: UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """List of conversations for a user."""

    conversations: list[ConversationSummary]
    total: int


class ConversationDetailResponse(BaseModel):
    """Full conversation with messages (paginated)."""

    id: UUID
    title: str
    messages: list["MessageResponse"]
    message_count: int
    page: int
    page_size: int
    has_next: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Message Schemas ──────────────────────────────────────────────────

class MessageResponse(BaseModel):
    """A single message in a conversation."""

    id: UUID
    role: str
    content: str
    status: Optional[str] = None
    citations: Optional[list[dict[str, Any]]] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    error_metadata: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedMessages(BaseModel):
    """Paginated list of messages in a conversation."""

    messages: list[MessageResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# ── Streaming Schemas ────────────────────────────────────────────────

class StreamEvent(BaseModel):
    """A single SSE event in the chat stream."""

    type: str = Field(
        ...,
        description="Event type: 'token', 'citation', 'done', 'error'",
    )
    content: Optional[str] = Field(None, description="Text content (for 'token' events)")
    citations: Optional[list[Citation]] = Field(None, description="Final citation list (for 'done' events)")
    conversation_id: Optional[UUID] = Field(None, description="Conversation ID (for 'done' or 'error' events)")
    message_id: Optional[UUID] = Field(None, description="Message ID (for 'done' or 'error' events)")
    detail: Optional[str] = Field(None, description="Error detail (for 'error' events)")


# ── Fix forward reference ────────────────────────────────────────────
ConversationDetailResponse.model_rebuild()
