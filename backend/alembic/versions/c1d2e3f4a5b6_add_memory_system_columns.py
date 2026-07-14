"""Add content, confidence, source_message_id, is_active to memories.

Extends the memories table for the Part 10 Memory System:
  - content: The actual memory content (replaces legacy key/value pattern)
  - confidence: Extraction model confidence score (0.0–1.0)
  - source_message_id: FK to the message that triggered extraction
  - is_active: Soft-active flag for prompt injection filtering

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-09 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add content column (replaces legacy key/value for new code)
    op.add_column(
        "memories",
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="The actual memory content (replaces key/value pattern)",
        ),
    )
    # Add confidence score
    op.add_column(
        "memories",
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="0.0",
            comment="Confidence score 0.0–1.0 from the extraction model",
        ),
    )
    # Add source_message_id FK
    op.add_column(
        "memories",
        sa.Column(
            "source_message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="The message that triggered this memory extraction",
        ),
    )
    op.create_foreign_key(
        "fk_memories_source_message_id",
        "memories",
        "messages",
        ["source_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Add is_active flag
    op.add_column(
        "memories",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Soft-active flag; inactive memories are excluded from prompts",
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_memories_source_message_id", "memories", type_="foreignkey"
    )
    op.drop_column("memories", "is_active")
    op.drop_column("memories", "source_message_id")
    op.drop_column("memories", "confidence")
    op.drop_column("memories", "content")
