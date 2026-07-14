"""Add chat system columns to messages table.

Adds support for:
  - Message lifecycle status (PENDING, COMPLETED, FAILED, CANCELLED)
  - Citation storage (JSON)
  - Token usage tracking
  - Error metadata capture

Revision ID: a1b2c3d4e5f6
Revises: f7e8d9a0b1c2
Create Date: 2026-07-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f7e8d9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create message_status enum type
    message_status_enum = sa.Enum(
        'PENDING', 'COMPLETED', 'FAILED', 'CANCELLED',
        name='message_status',
    )
    message_status_enum.create(op.get_bind(), checkfirst=True)

    # Add columns
    op.add_column('messages', sa.Column(
        'status',
        message_status_enum,
        nullable=True,
        comment='Lifecycle status for ASSISTANT messages',
    ))
    op.add_column('messages', sa.Column(
        'citations',
        sa.JSON(),
        nullable=True,
        comment='Citation list from the RAG pipeline',
    ))
    op.add_column('messages', sa.Column(
        'error_metadata',
        sa.JSON(),
        nullable=True,
        comment='Error details if status == FAILED',
    ))
    op.add_column('messages', sa.Column(
        'prompt_tokens',
        sa.Integer(),
        nullable=True,
    ))
    op.add_column('messages', sa.Column(
        'completion_tokens',
        sa.Integer(),
        nullable=True,
    ))
    op.add_column('messages', sa.Column(
        'total_tokens',
        sa.Integer(),
        nullable=True,
    ))


def downgrade() -> None:
    op.drop_column('messages', 'total_tokens')
    op.drop_column('messages', 'completion_tokens')
    op.drop_column('messages', 'prompt_tokens')
    op.drop_column('messages', 'error_metadata')
    op.drop_column('messages', 'citations')
    op.drop_column('messages', 'status')

    # Drop enum type
    sa.Enum(name='message_status').drop(op.get_bind(), checkfirst=True)
