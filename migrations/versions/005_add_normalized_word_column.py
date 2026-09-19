"""Add normalized_word column to blacklists for efficient Unicode-aware matching

Revision ID: 005
Revises: 004
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the normalized_word column (nullable initially to allow existing rows)
    op.add_column(
        "blacklists",
        sa.Column("normalized_word", sa.Text(), nullable=True)
    )
    # Note: The index on (group_id, normalized_word) is defined in the SQLAlchemy
    # model's __table_args__ and will be created automatically by Alembic's
    # autogenerate or when the model is used to create tables.


def downgrade() -> None:
    op.drop_column("blacklists", "normalized_word")
