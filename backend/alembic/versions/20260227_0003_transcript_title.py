"""add transcript title

Revision ID: 20260227_0003
Revises: 20260226_0002
Create Date: 2026-02-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260227_0003"
down_revision: Union[str, None] = "20260226_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transcripts", sa.Column("title", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("transcripts", "title")
