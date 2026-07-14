"""create quiz_questions table and extend quiz_attempts

Adds:
  - quiz_questions table with FK to quizzes and chunks
  - user_id to quiz_attempts
  - answers, correct_answers, completed_at columns to quiz_attempts

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-10 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create quiz_questions table
    op.create_table(
        "quiz_questions",
        sa.Column("quiz_id", sa.UUID(), nullable=False),
        sa.Column("source_chunk_id", sa.UUID(), nullable=True),
        sa.Column("question_type", sa.String(20), nullable=False, server_default="multiple_choice"),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options", sa.Text(), nullable=True, comment="JSON-encoded list of options for MCQ"),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_quiz_questions_quiz_id"),
        "quiz_questions",
        ["quiz_id"],
    )
    op.create_index(
        op.f("ix_quiz_questions_source_chunk_id"),
        "quiz_questions",
        ["source_chunk_id"],
    )

    # Add user_id to quiz_attempts
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "user_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_quiz_attempts_user_id"),
        "quiz_attempts",
        ["user_id"],
    )
    op.create_foreign_key(
        "fk_quiz_attempts_user_id_users",
        "quiz_attempts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add answers column
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "answers",
            sa.Text(),
            nullable=True,
            comment="JSON-encoded list of user answers",
        ),
    )

    # Add correct_answers column
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "correct_answers",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Add completed_at column
    op.add_column(
        "quiz_attempts",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Drop quiz_questions table
    op.drop_index(op.f("ix_quiz_questions_source_chunk_id"), table_name="quiz_questions")
    op.drop_index(op.f("ix_quiz_questions_quiz_id"), table_name="quiz_questions")
    op.drop_table("quiz_questions")

    # Revert quiz_attempts changes
    op.drop_column("quiz_attempts", "completed_at")
    op.drop_column("quiz_attempts", "correct_answers")
    op.drop_column("quiz_attempts", "answers")
    op.drop_index(op.f("ix_quiz_attempts_user_id"), table_name="quiz_attempts")
    op.drop_constraint("fk_quiz_attempts_user_id_users", "quiz_attempts", type_="foreignkey")
    op.drop_column("quiz_attempts", "user_id")
