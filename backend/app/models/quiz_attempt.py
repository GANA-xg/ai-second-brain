import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


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

    score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    total_questions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    quiz: Mapped["Quiz"] = relationship(
        back_populates="attempts",
    )