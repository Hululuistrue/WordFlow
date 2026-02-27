"""add youtube_mode to jobs

Revision ID: 20260227_0005
Revises: 20260227_0004
Create Date: 2026-02-27 16:45:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260227_0005"
down_revision = "20260227_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("youtube_mode", sa.String(length=16), nullable=False, server_default="compat"),
    )


def downgrade() -> None:
    op.drop_column("jobs", "youtube_mode")
