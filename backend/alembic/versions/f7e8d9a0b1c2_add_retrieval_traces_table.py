"""Add retrieval_traces table for RAG observability.

Revision ID: f7e8d9a0b1c2
Revises: d1e2f3a4b5c6
Create Date: 2026-07-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f7e8d9a0b1c2'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'retrieval_traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('embedding_model', sa.String(255), nullable=False),
        sa.Column('prompt_version', sa.String(50), nullable=False),
        sa.Column('gemini_model', sa.String(255), nullable=False),
        sa.Column('top_k', sa.Integer(), nullable=False),
        sa.Column('score_threshold', sa.Float(), nullable=False, server_default='0.0'),
        # Use JSON for cross-DB compatibility
        sa.Column('retrieved_chunk_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('document_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('retrieval_scores', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('retrieval_latency_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('gemini_prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gemini_completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gemini_total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gemini_latency_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_latency_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('retrieval_traces')
