"""add youtube_client to jobs

Revision ID: 20260227_0004
Revises: 20260227_0003
Create Date: 2026-02-27 11:35:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260227_0004"
down_revision = "20260227_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("youtube_client", sa.String(length=32), nullable=False, server_default="web"),
    )


def downgrade() -> None:
    op.drop_column("jobs", "youtube_client")
