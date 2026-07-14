"""add source_chunk_id to flashcards

Note: difficulty column was already added by the 2b21c55ea802 migration
(create quizzes and quiz attempts tables). This migration only adds
the source_chunk_id column and its FK/index.

Revision ID: f1a2b3c4d5e6
Revises: c1d2e3f4a5b6
Create Date: 2026-07-10 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source_chunk_id column (difficulty was already added by 2b21c55ea802)
    op.add_column(
        "flashcards",
        sa.Column(
            "source_chunk_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_flashcards_source_chunk_id_chunks",
        "flashcards",
        "chunks",
        ["source_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_flashcards_source_chunk_id"),
        "flashcards",
        ["source_chunk_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_flashcards_source_chunk_id"),
        table_name="flashcards",
    )
    op.drop_constraint(
        "fk_flashcards_source_chunk_id_chunks",
        "flashcards",
        type_="foreignkey",
    )
    op.drop_column("flashcards", "source_chunk_id")
