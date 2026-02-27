"""v2 initial schema

Revision ID: 20260226_0001
Revises:
Create Date: 2026-02-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260226_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "uploads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploads_workspace_id", "uploads", ["workspace_id"])

    op.create_table(
        "source_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=120), nullable=True),
        sa.Column("youtube_url", sa.String(length=500), nullable=True),
        sa.Column("upload_object_key", sa.String(length=500), nullable=True),
        sa.Column("upload_filename", sa.String(length=255), nullable=True),
        sa.Column("media_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_assets_workspace_id", "source_assets", ["workspace_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("source_asset_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("language_pref", sa.String(length=32), nullable=False),
        sa.Column("with_timestamps", sa.Boolean(), nullable=False),
        sa.Column("engine", sa.String(length=80), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_asset_id"], ["source_assets.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_workspace_id", "jobs", ["workspace_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "transcripts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("source_label", sa.String(length=80), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("latest_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_transcripts_job_id", "transcripts", ["job_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcript_segments_transcript_id", "transcript_segments", ["transcript_id"])

    op.create_table(
        "transcript_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("edit_status", sa.String(length=20), nullable=False),
        sa.Column("edited_text", sa.Text(), nullable=False),
        sa.Column("editor_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcript_versions_transcript_id", "transcript_versions", ["transcript_id"])

    op.create_table(
        "exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("transcript_version_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transcript_version_id"], ["transcript_versions.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exports_workspace_id", "exports", ["workspace_id"])
    op.create_index("ix_exports_transcript_version_id", "exports", ["transcript_version_id"])

    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("usage_minutes", sa.Float(), nullable=False),
        sa.Column("usage_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_ledger_workspace_id", "usage_ledger", ["workspace_id"])

    op.create_table(
        "abuse_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("reporter_email", sa.String(length=255), nullable=True),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuse_reports_workspace_id", "abuse_reports", ["workspace_id"])
    op.create_index("ix_abuse_reports_job_id", "abuse_reports", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_abuse_reports_job_id", table_name="abuse_reports")
    op.drop_index("ix_abuse_reports_workspace_id", table_name="abuse_reports")
    op.drop_table("abuse_reports")

    op.drop_index("ix_usage_ledger_workspace_id", table_name="usage_ledger")
    op.drop_table("usage_ledger")

    op.drop_index("ix_exports_transcript_version_id", table_name="exports")
    op.drop_index("ix_exports_workspace_id", table_name="exports")
    op.drop_table("exports")

    op.drop_index("ix_transcript_versions_transcript_id", table_name="transcript_versions")
    op.drop_table("transcript_versions")

    op.drop_index("ix_transcript_segments_transcript_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")

    op.drop_index("ix_transcripts_job_id", table_name="transcripts")
    op.drop_table("transcripts")

    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_workspace_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_source_assets_workspace_id", table_name="source_assets")
    op.drop_table("source_assets")

    op.drop_index("ix_uploads_workspace_id", table_name="uploads")
    op.drop_table("uploads")

    op.drop_table("workspaces")

