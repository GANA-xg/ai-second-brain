"""add metadata columns to chunks

Add source_type, page_number, slide_number, section, character_start,
character_end, token_estimate columns to support the document processing
pipeline. Also make token_count nullable (it will be populated later by
the embedding phase).

Revision ID: ad5f3c9e4b12
Revises: 9c5f695c6ff2
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad5f3c9e4b12'
down_revision: Union[str, None] = '9c5f695c6ff2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old token_count > 0 constraint (will be replaced)
    op.drop_constraint('ck_chunks_token_count_positive', 'chunks', type_='check')

    # Add new columns (all nullable first to handle existing data, then alter)
    op.add_column('chunks', sa.Column('source_type', sa.String(length=20), nullable=True))
    op.add_column('chunks', sa.Column('page_number', sa.Integer(), nullable=True))
    op.add_column('chunks', sa.Column('slide_number', sa.Integer(), nullable=True))
    op.add_column('chunks', sa.Column('section', sa.String(length=255), nullable=True))
    op.add_column('chunks', sa.Column('character_start', sa.Integer(), nullable=True))
    op.add_column('chunks', sa.Column('character_end', sa.Integer(), nullable=True))
    op.add_column('chunks', sa.Column('token_estimate', sa.Integer(), nullable=True))

    # Make token_count nullable
    op.alter_column('chunks', 'token_count', nullable=True)

    # Set default values for existing rows (should be none in prod, but safe)
    op.execute("UPDATE chunks SET source_type = 'unknown' WHERE source_type IS NULL")
    op.execute("UPDATE chunks SET character_start = 0 WHERE character_start IS NULL")
    op.execute("UPDATE chunks SET character_end = 0 WHERE character_end IS NULL")
    op.execute("UPDATE chunks SET token_estimate = 1 WHERE token_estimate IS NULL")

    # Now make non-nullable columns actually non-nullable
    op.alter_column('chunks', 'source_type', nullable=False)
    op.alter_column('chunks', 'character_start', nullable=False)
    op.alter_column('chunks', 'character_end', nullable=False)
    op.alter_column('chunks', 'token_estimate', nullable=False)

    # Add new constraints
    op.create_check_constraint(
        'ck_chunks_character_range_valid',
        'chunks',
        sa.text('character_end > character_start'),
    )
    op.create_check_constraint(
        'ck_chunks_token_estimate_positive',
        'chunks',
        sa.text('token_estimate > 0'),
    )


def downgrade() -> None:
    # Drop new constraints
    op.drop_constraint('ck_chunks_token_estimate_positive', 'chunks', type_='check')
    op.drop_constraint('ck_chunks_character_range_valid', 'chunks', type_='check')

    # Drop new columns
    op.drop_column('chunks', 'token_estimate')
    op.drop_column('chunks', 'character_end')
    op.drop_column('chunks', 'character_start')
    op.drop_column('chunks', 'section')
    op.drop_column('chunks', 'slide_number')
    op.drop_column('chunks', 'page_number')
    op.drop_column('chunks', 'source_type')

    # Restore token_count to non-nullable
    op.execute("UPDATE chunks SET token_count = 1 WHERE token_count IS NULL")
    op.alter_column('chunks', 'token_count', nullable=False)

    # Restore original constraint
    op.create_check_constraint(
        'ck_chunks_token_count_positive',
        'chunks',
        sa.text('token_count > 0'),
    )
