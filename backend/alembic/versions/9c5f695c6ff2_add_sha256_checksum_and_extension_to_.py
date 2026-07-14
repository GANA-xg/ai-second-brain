"""add sha256_checksum and extension to documents

Revision ID: 9c5f695c6ff2
Revises: 819514a3e128
Create Date: 2026-07-07 21:55:12.124632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c5f695c6ff2'
down_revision: Union[str, None] = '819514a3e128'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('sha256_checksum', sa.String(length=64), nullable=True))
    op.add_column('documents', sa.Column('extension', sa.String(length=20), nullable=False))


def downgrade() -> None:
    op.drop_column('documents', 'extension')
    op.drop_column('documents', 'sha256_checksum')
