"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-09-11 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # groups table
    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_groups_telegram_id", "groups", ["telegram_id"])

    # group_settings table
    op.create_table(
        "group_settings",
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("warn_limit", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("welcome_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("goodbye_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("anti_flood_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("anti_spam_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("log_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rules", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id"),
    )

    # members table
    op.create_table(
        "members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "telegram_id", name="uq_group_telegram_member"),
    )
    op.create_index("ix_members_group_id", "members", ["group_id"])
    op.create_index("ix_members_telegram_id", "members", ["telegram_id"])

    # warnings table
    op.create_table(
        "warnings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("issued_by", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_warnings_group_id", "warnings", ["group_id"])
    op.create_index("ix_warnings_user_id", "warnings", ["user_id"])

    # filters table
    op.create_table(
        "filters",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("trigger", sa.String(255), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False, server_default="reply"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "trigger", name="uq_group_filter_trigger"),
    )
    op.create_index("ix_filters_group_id", "filters", ["group_id"])

    # audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_group_id", "audit_logs", ["group_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_target_id", "audit_logs", ["target_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("filters")
    op.drop_table("warnings")
    op.drop_table("members")
    op.drop_table("group_settings")
    op.drop_table("groups")
