"""Add profile fields to users table

Revision ID: a1b2c3d4e5f8
Revises: 2f377b438f31
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, None] = "2f377b438f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("bio", sa.String(1000), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(2048), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "bio")
    op.drop_column("users", "username")
