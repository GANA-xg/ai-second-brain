"""add chunk_embeddings table

Create the chunk_embeddings table to store generated embedding vectors
with full version metadata for deterministic, idempotent re-embedding.

Revision ID: d1e2f3a4b5c6
Revises: ad5f3c9e4b12
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'ad5f3c9e4b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chunk_embeddings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('chunk_id', sa.UUID(), nullable=False),
        sa.Column('embedding', sa.LargeBinary(), nullable=False),
        sa.Column('embedding_model', sa.String(length=255), nullable=False),
        sa.Column('embedding_version', sa.String(length=50), nullable=False),
        sa.Column('embedding_dimension', sa.Integer(), nullable=False),
        sa.Column('magnitude', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['chunk_id'],
            ['chunks.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'chunk_id',
            'embedding_version',
            name='uq_chunk_embeddings_chunk_version',
        ),
    )
    op.create_index(
        op.f('ix_chunk_embeddings_chunk_id'),
        'chunk_embeddings',
        ['chunk_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_chunk_embeddings_chunk_id'),
        table_name='chunk_embeddings',
    )
    op.drop_table('chunk_embeddings')
