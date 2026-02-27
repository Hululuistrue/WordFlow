"""add youtube cookies fields to jobs

Revision ID: 20260226_0002
Revises: 20260226_0001
Create Date: 2026-02-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260226_0002"
down_revision: Union[str, None] = "20260226_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("youtube_use_cookies", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("jobs", sa.Column("youtube_cookies_txt", sa.Text(), nullable=True))
    op.alter_column("jobs", "youtube_use_cookies", server_default=None)


def downgrade() -> None:
    op.drop_column("jobs", "youtube_cookies_txt")
    op.drop_column("jobs", "youtube_use_cookies")
