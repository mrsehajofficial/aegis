"""Create business_connections and business_rules tables

Revision ID: 006
Revises: 005
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("can_reply", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("auto_reply_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("greeting_enabled", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("greeting_message", sa.Text(), nullable=True),
        sa.Column("away_enabled", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("away_message", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id"),
    )
    op.create_index(op.f("ix_business_connections_connection_id"), "business_connections", ["connection_id"], unique=True)
    op.create_index(op.f("ix_business_connections_user_id"), "business_connections", ["user_id"], unique=False)

    op.create_table(
        "business_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("connection_id", sa.String(length=128), nullable=True),
        sa.Column("trigger", sa.String(length=255), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("match_type", sa.String(length=32), server_default="contains", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["business_connections.connection_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_business_rules_user_id"), "business_rules", ["user_id"], unique=False)
    op.create_index(op.f("ix_business_rules_connection_id"), "business_rules", ["connection_id"], unique=False)


def downgrade() -> None:
    op.drop_table("business_rules")
    op.drop_table("business_connections")
