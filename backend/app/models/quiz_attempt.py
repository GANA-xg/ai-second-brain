import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.quiz import Quiz
    from app.models.user import User


class QuizAttempt(BaseModel):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        Index(
            "ix_quiz_attempts_quiz_created",
            "quiz_id",
            "created_at",
        ),
        CheckConstraint(
            "score >= 0",
            name="ck_quiz_attempts_score_non_negative",
        ),
        CheckConstraint(
            "total_questions > 0",
            name="ck_quiz_attempts_total_questions_positive",
        ),
    )

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    total_questions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    correct_answers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    answers: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="JSON-encoded list of user answers",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    quiz: Mapped["Quiz"] = relationship(
        back_populates="attempts",
    )

    user: Mapped["User"] = relationship(
        back_populates="quiz_attempts",
    )
