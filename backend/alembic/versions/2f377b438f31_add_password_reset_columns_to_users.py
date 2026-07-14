"""add password reset columns to users

Revision ID: 2f377b438f31
Revises: 71f3a8b2c9d0
Create Date: 2026-07-10 18:38:46.216039

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2f377b438f31'
down_revision: Union[str, None] = '71f3a8b2c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_reset_token_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('password_reset_token_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_reset_token_expires_at')
    op.drop_column('users', 'password_reset_token_hash')
