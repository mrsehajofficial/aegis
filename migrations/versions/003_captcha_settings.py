"""Add join-captcha settings to group_settings

Revision ID: 003
Revises: 002
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "group_settings",
        sa.Column(
            "captcha_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "group_settings",
        sa.Column(
            "captcha_timeout_seconds", sa.Integer(), nullable=False, server_default="120"
        ),
    )
    op.add_column(
        "group_settings",
        sa.Column("captcha_action", sa.String(16), nullable=False, server_default="kick"),
    )


def downgrade() -> None:
    op.drop_column("group_settings", "captcha_action")
    op.drop_column("group_settings", "captcha_timeout_seconds")
    op.drop_column("group_settings", "captcha_enabled")
