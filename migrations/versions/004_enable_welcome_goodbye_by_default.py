"""Enable welcome/goodbye messages by default

Revision ID: 004
Revises: 003
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable welcome and goodbye messages for all existing groups
    op.execute("UPDATE group_settings SET welcome_enabled = true WHERE welcome_enabled = false")
    op.execute("UPDATE group_settings SET goodbye_enabled = true WHERE goodbye_enabled = false")
    # Update the column defaults for future groups
    op.alter_column("group_settings", "welcome_enabled", server_default="true")
    op.alter_column("group_settings", "goodbye_enabled", server_default="true")


def downgrade() -> None:
    # Disable welcome and goodbye messages (revert to original behavior)
    op.execute("UPDATE group_settings SET welcome_enabled = false")
    op.execute("UPDATE group_settings SET goodbye_enabled = false")
    op.alter_column("group_settings", "welcome_enabled", server_default="false")
    op.alter_column("group_settings", "goodbye_enabled", server_default="false")
