"""Retrieval trace model for RAG observability."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class RetrievalTrace(BaseModel):
    """Stores a retrieval trace for every RAG request.

    Used for debugging retrieval quality, latency analysis, and audit.
    One trace per RAG question-answer cycle.
    """

    __tablename__ = "retrieval_traces"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # Query details
    question: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    gemini_model: Mapped[str] = mapped_column(String(255), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    score_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Retrieval results (JSON for cross-DB compatibility: SQLite + PostgreSQL)
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    document_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    retrieval_scores: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)

    # Latency breakdown (ms)
    retrieval_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gemini_prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gemini_completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gemini_total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gemini_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="retrieval_traces")

    def __repr__(self) -> str:
        return f"<RetrievalTrace {self.id} user={self.user_id} conversation={self.conversation_id}>"
