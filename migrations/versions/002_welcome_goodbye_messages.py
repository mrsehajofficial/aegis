"""Add welcome/goodbye message text columns

Revision ID: 002
Revises: 001
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("group_settings", sa.Column("welcome_message", sa.Text(), nullable=True))
    op.add_column("group_settings", sa.Column("goodbye_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("group_settings", "goodbye_message")
    op.drop_column("group_settings", "welcome_message")