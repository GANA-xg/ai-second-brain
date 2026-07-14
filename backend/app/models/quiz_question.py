import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.quiz import Quiz


class QuizQuestion(BaseModel):
    __tablename__ = "quiz_questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    question_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="multiple_choice",
    )

    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    options: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="JSON-encoded list of options for MCQ",
    )

    correct_answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    explanation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    order_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    difficulty: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
    )

    quiz: Mapped["Quiz"] = relationship(
        back_populates="questions",
    )

    source_chunk: Mapped["Chunk"] = relationship(
        back_populates="quiz_questions",
    )
