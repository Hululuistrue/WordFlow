from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
import re
from uuid import uuid4

from sqlalchemy import Select, delete, desc, func, select
from sqlalchemy.orm import Session

from app.api.v2.schemas import (
    AbuseReport,
    AbuseReportCreateRequest,
    AbuseStatus,
    ExportAsset,
    ExportCreateRequest,
    Job,
    JobCreateRequest,
    JobStatus,
    TranscriptDetail,
    TranscriptPatchRequest,
    TranscriptSegment,
    TranscriptVersion,
    TranscriptVersionStatus,
    Workspace,
)
from app.core.config import get_settings
from app.db.models import (
    AbuseReportModel,
    ExportModel,
    JobModel,
    SourceAssetModel,
    TranscriptModel,
    TranscriptSegmentModel,
    TranscriptVersionModel,
    UploadModel,
    UsageLedgerModel,
    WorkspaceModel,
)


def _new_id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_timestamp(seconds: float, sep: str = ",") -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    secs = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _export_extension(fmt: str) -> str:
    if fmt == "text":
        return "txt"
    return fmt


def _safe_export_basename(title: str | None) -> str:
    raw = (title or "transcript").strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if not cleaned:
        return "transcript"
    return cleaned[:120]


def _render_export_content(
    fmt: str,
    transcript: TranscriptModel,
    version: TranscriptVersionModel,
    segments: list[TranscriptSegmentModel],
) -> str:
    text_body = version.edited_text.strip()
    if fmt in {"text", "txt"}:
        return text_body + "\n"

    if fmt == "md":
        title = transcript.title or transcript.source_label or "Transcript Export"
        language = transcript.language or "unknown"
        lines = [
            f"# {title}",
            "",
            f"- Transcript ID: `{transcript.id}`",
            f"- Language: `{language}`",
            f"- Version: `{version.version_number}`",
            "",
            "## Content",
            "",
            text_body,
            "",
        ]
        return "\n".join(lines)

    if fmt == "srt":
        blocks: list[str] = []
        for index, seg in enumerate(segments, start=1):
            blocks.append(
                "\n".join(
                    [
                        str(index),
                        f"{_format_timestamp(seg.start_seconds)} --> {_format_timestamp(seg.end_seconds)}",
                        seg.text.strip(),
                    ]
                )
            )
        return "\n\n".join(blocks).strip() + "\n"

    if fmt == "vtt":
        blocks = ["WEBVTT", ""]
        for seg in segments:
            blocks.append(
                "\n".join(
                    [
                        f"{_format_timestamp(seg.start_seconds, sep='.')} --> {_format_timestamp(seg.end_seconds, sep='.')}",
                        seg.text.strip(),
                        "",
                    ]
                )
            )
        return "\n".join(blocks).rstrip() + "\n"

    raise ValueError(f"Unsupported export format: {fmt}")


def _to_workspace(model: WorkspaceModel) -> Workspace:
    return Workspace(
        id=model.id,
        name=model.name,
        owner_user_id=model.owner_user_id,
        created_at=model.created_at,
    )


def _to_job(model: JobModel) -> Job:
    return Job(
        id=model.id,
        workspace_id=model.workspace_id,
        project_id=model.project_id,
        source_type=model.source_type,
        youtube_client=model.youtube_client,
        youtube_mode=model.youtube_mode,
        youtube_use_cookies=model.youtube_use_cookies,
        status=model.status,
        progress=model.progress,
        error_code=model.error_code,
        error_message=model.error_message,
        created_at=model.created_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        transcript_id=model.transcript_id,
    )


@dataclass
class JobProcessingContext:
    job_id: str
    workspace_id: str
    source_type: str
    source_asset_id: str | None
    upload_object_key: str | None
    upload_filename: str | None
    youtube_video_id: str | None
    youtube_client: str
    youtube_mode: str
    youtube_use_cookies: bool
    youtube_cookies_txt: str | None
    language_pref: str
    with_timestamps: bool


class V2Repository:
    def __init__(self, db: Session):
        self.db = db

    def create_workspace(self, name: str, owner_user_id: str) -> Workspace:
        model = WorkspaceModel(
            id=_new_id(),
            name=name,
            owner_user_id=owner_user_id,
            created_at=_now(),
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _to_workspace(model)

    def list_workspaces(self) -> list[Workspace]:
        items = self.db.execute(select(WorkspaceModel).order_by(desc(WorkspaceModel.created_at))).scalars().all()
        return [_to_workspace(item) for item in items]

    def workspace_exists(self, workspace_id: str) -> bool:
        return self.db.get(WorkspaceModel, workspace_id) is not None

    def create_upload(self, workspace_id: str, filename: str, content_type: str, size_bytes: int) -> UploadModel:
        upload_id = _new_id()
        model = UploadModel(
            id=upload_id,
            workspace_id=workspace_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            object_key=f"uploads/{workspace_id}/{upload_id}/{filename}",
            created_at=_now(),
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def complete_upload(self, upload_id: str) -> str:
        upload = self.db.get(UploadModel, upload_id)
        if not upload:
            raise KeyError("Upload not found")
        source_asset_id = _new_id()
        source_asset = SourceAssetModel(
            id=source_asset_id,
            workspace_id=upload.workspace_id,
            source_type="upload",
            upload_object_key=upload.object_key,
            upload_filename=upload.filename,
            created_at=_now(),
        )
        self.db.add(source_asset)
        self.db.commit()
        return source_asset_id

    def get_upload(self, upload_id: str) -> UploadModel | None:
        return self.db.get(UploadModel, upload_id)

    def update_upload_object_key(self, upload_id: str, object_key: str, size_bytes: int | None = None) -> UploadModel:
        upload = self.db.get(UploadModel, upload_id)
        if not upload:
            raise KeyError("Upload not found")
        upload.object_key = object_key
        if size_bytes is not None:
            upload.size_bytes = size_bytes
        self.db.add(upload)
        self.db.commit()
        self.db.refresh(upload)
        return upload

    def source_asset_exists(self, source_asset_id: str) -> bool:
        return self.db.get(SourceAssetModel, source_asset_id) is not None

    def create_job(self, payload: JobCreateRequest, created_by: str) -> Job:
        now = _now()
        job_id = _new_id()

        job = JobModel(
            id=job_id,
            workspace_id=payload.workspace_id,
            project_id=payload.project_id,
            source_asset_id=payload.source_asset_id,
            source_type=payload.source_type.value,
            youtube_video_id=payload.youtube_video_id,
            youtube_client=payload.youtube_client.value,
            youtube_mode=payload.youtube_mode.value,
            youtube_use_cookies=payload.youtube_use_cookies,
            youtube_cookies_txt=payload.youtube_cookies_txt,
            status=JobStatus.queued.value,
            progress=0,
            language_pref=payload.language_pref,
            with_timestamps=payload.with_timestamps,
            engine=None,
            created_by=created_by,
            transcript_id=None,
            created_at=now,
            started_at=None,
            finished_at=None,
        )
        self.db.add(job)

        self.db.commit()
        self.db.refresh(job)
        return _to_job(job)

    def get_job_processing_context(self, job_id: str) -> JobProcessingContext | None:
        model = self.db.get(JobModel, job_id)
        if not model:
            return None
        source_asset = self.db.get(SourceAssetModel, model.source_asset_id) if model.source_asset_id else None
        return JobProcessingContext(
            job_id=model.id,
            workspace_id=model.workspace_id,
            source_type=model.source_type,
            source_asset_id=model.source_asset_id,
            upload_object_key=source_asset.upload_object_key if source_asset else None,
            upload_filename=source_asset.upload_filename if source_asset else None,
            youtube_video_id=model.youtube_video_id,
            youtube_client=model.youtube_client,
            youtube_mode=model.youtube_mode,
            youtube_use_cookies=model.youtube_use_cookies,
            youtube_cookies_txt=model.youtube_cookies_txt,
            language_pref=model.language_pref,
            with_timestamps=model.with_timestamps,
        )

    def mark_job_running(self, job_id: str) -> Job:
        model = self.db.get(JobModel, job_id)
        if not model:
            raise KeyError("Job not found")
        if model.status == JobStatus.canceled.value:
            return _to_job(model)
        model.status = JobStatus.running.value
        model.progress = 20
        model.started_at = _now()
        model.finished_at = None
        model.error_code = None
        model.error_message = None
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _to_job(model)

    def mark_job_success(
        self,
        job_id: str,
        editor_user_id: str,
        title: str | None,
        source_label: str,
        language: str | None,
        raw_text: str,
        segments: list[TranscriptSegment],
        engine: str,
    ) -> Job:
        model = self.db.get(JobModel, job_id)
        if not model:
            raise KeyError("Job not found")
        if model.status == JobStatus.canceled.value:
            return _to_job(model)

        now = _now()
        transcript = self.db.execute(select(TranscriptModel).where(TranscriptModel.job_id == model.id)).scalar_one_or_none()
        if transcript is None:
            transcript = TranscriptModel(
                id=_new_id(),
                job_id=model.id,
                title=title,
                language=language,
                source_label=source_label,
                raw_text=raw_text,
                latest_version_id=None,
                created_at=now,
            )
            self.db.add(transcript)
            transcript_id = transcript.id
            next_version_number = 1
        else:
            transcript_id = transcript.id
            transcript.language = language
            transcript.title = title
            transcript.source_label = source_label
            transcript.raw_text = raw_text
            self.db.execute(delete(TranscriptSegmentModel).where(TranscriptSegmentModel.transcript_id == transcript_id))
            max_version = self.db.execute(
                select(func.max(TranscriptVersionModel.version_number)).where(
                    TranscriptVersionModel.transcript_id == transcript_id
                )
            ).scalar_one()
            next_version_number = int(max_version or 0) + 1

        for seg in segments:
            self.db.add(
                TranscriptSegmentModel(
                    id=_new_id(),
                    transcript_id=transcript_id,
                    segment_index=seg.index,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                    text=seg.text,
                )
            )

        version = TranscriptVersionModel(
            id=_new_id(),
            transcript_id=transcript_id,
            version_number=next_version_number,
            edit_status=TranscriptVersionStatus.draft.value,
            edited_text=raw_text,
            editor_user_id=editor_user_id,
            created_at=now,
        )
        self.db.add(version)
        transcript.latest_version_id = version.id

        model.status = JobStatus.success.value
        model.progress = 100
        model.engine = engine
        model.transcript_id = transcript_id
        model.finished_at = now
        model.youtube_cookies_txt = None
        model.error_code = None
        model.error_message = None
        self.db.add(model)

        self.db.add(
            UsageLedgerModel(
                id=_new_id(),
                workspace_id=model.workspace_id,
                job_id=model.id,
                usage_minutes=0.1,
                usage_type="transcription",
                created_at=now,
            )
        )

        self.db.commit()
        self.db.refresh(model)
        return _to_job(model)

    def mark_job_failed(self, job_id: str, error_code: str, error_message: str) -> Job:
        model = self.db.get(JobModel, job_id)
        if not model:
            raise KeyError("Job not found")
        model.status = JobStatus.failed.value
        model.progress = 100
        model.error_code = error_code
        model.error_message = error_message
        model.finished_at = _now()
        model.youtube_cookies_txt = None
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _to_job(model)

    def list_jobs(self, workspace_id: str, status_filter: JobStatus | None, limit: int, cursor: str | None) -> tuple[list[Job], str | None]:
        query: Select[tuple[JobModel]] = select(JobModel).where(JobModel.workspace_id == workspace_id).order_by(desc(JobModel.created_at))
        if status_filter is not None:
            query = query.where(JobModel.status == status_filter.value)
        if cursor:
            cursor_model = self.db.get(JobModel, cursor)
            if cursor_model is not None:
                query = query.where(JobModel.created_at < cursor_model.created_at)

        rows = self.db.execute(query.limit(limit + 1)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [_to_job(row) for row in page]
        next_cursor = items[-1].id if has_more and items else None
        return items, next_cursor

    def get_job(self, job_id: str) -> Job | None:
        model = self.db.get(JobModel, job_id)
        if not model:
            return None
        return _to_job(model)

    def retry_job(self, job_id: str) -> Job:
        model = self.db.get(JobModel, job_id)
        if not model:
            raise KeyError("Job not found")
        model.status = JobStatus.queued.value
        model.progress = 0
        model.error_code = None
        model.error_message = None
        model.transcript_id = None
        model.youtube_cookies_txt = None
        model.started_at = None
        model.finished_at = None
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _to_job(model)

    def cancel_job(self, job_id: str) -> Job:
        model = self.db.get(JobModel, job_id)
        if not model:
            raise KeyError("Job not found")
        model.status = JobStatus.canceled.value
        model.progress = 100
        model.finished_at = _now()
        model.youtube_cookies_txt = None
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return _to_job(model)

    def get_transcript(self, transcript_id: str) -> TranscriptDetail | None:
        transcript = self.db.get(TranscriptModel, transcript_id)
        if not transcript:
            return None

        latest_version = self.db.get(TranscriptVersionModel, transcript.latest_version_id) if transcript.latest_version_id else None
        if latest_version is None:
            return None

        segments = self.db.execute(
            select(TranscriptSegmentModel)
            .where(TranscriptSegmentModel.transcript_id == transcript_id)
            .order_by(TranscriptSegmentModel.segment_index)
        ).scalars().all()

        return TranscriptDetail(
            id=transcript.id,
            job_id=transcript.job_id,
            title=transcript.title,
            language=transcript.language,
            source_label=transcript.source_label,
            raw_text=transcript.raw_text,
            segments=[
                TranscriptSegment(
                    index=item.segment_index,
                    start_seconds=item.start_seconds,
                    end_seconds=item.end_seconds,
                    text=item.text,
                )
                for item in segments
            ],
            latest_version=TranscriptVersion(
                id=latest_version.id,
                transcript_id=latest_version.transcript_id,
                version_number=latest_version.version_number,
                edit_status=latest_version.edit_status,
                edited_text=latest_version.edited_text,
                editor_user_id=latest_version.editor_user_id,
                created_at=latest_version.created_at,
            ),
        )

    def update_transcript(self, transcript_id: str, payload: TranscriptPatchRequest, editor_user_id: str) -> TranscriptVersion:
        transcript = self.db.get(TranscriptModel, transcript_id)
        if not transcript:
            raise KeyError("Transcript not found")

        max_version = self.db.execute(
            select(func.max(TranscriptVersionModel.version_number)).where(TranscriptVersionModel.transcript_id == transcript_id)
        ).scalar_one()
        next_version = int(max_version or 0) + 1

        version = TranscriptVersionModel(
            id=_new_id(),
            transcript_id=transcript_id,
            version_number=next_version,
            edit_status=TranscriptVersionStatus.draft.value,
            edited_text=payload.edited_text,
            editor_user_id=editor_user_id,
            created_at=_now(),
        )
        self.db.add(version)
        transcript.latest_version_id = version.id
        transcript.raw_text = payload.edited_text
        self.db.add(transcript)
        self.db.commit()
        self.db.refresh(version)

        return TranscriptVersion(
            id=version.id,
            transcript_id=version.transcript_id,
            version_number=version.version_number,
            edit_status=version.edit_status,
            edited_text=version.edited_text,
            editor_user_id=version.editor_user_id,
            created_at=version.created_at,
        )

    def publish_version(self, transcript_id: str, version_id: str) -> TranscriptVersion:
        version = self.db.get(TranscriptVersionModel, version_id)
        if not version:
            raise KeyError("Version not found")
        if version.transcript_id != transcript_id:
            raise KeyError("Version does not belong to transcript")
        version.edit_status = TranscriptVersionStatus.published.value
        self.db.add(version)

        transcript = self.db.get(TranscriptModel, transcript_id)
        if transcript:
            transcript.latest_version_id = version.id
            self.db.add(transcript)

        self.db.commit()
        self.db.refresh(version)
        return TranscriptVersion(
            id=version.id,
            transcript_id=version.transcript_id,
            version_number=version.version_number,
            edit_status=version.edit_status,
            edited_text=version.edited_text,
            editor_user_id=version.editor_user_id,
            created_at=version.created_at,
        )

    def transcript_version_exists(self, version_id: str) -> bool:
        return self.db.get(TranscriptVersionModel, version_id) is not None

    def create_export(self, payload: ExportCreateRequest) -> ExportAsset:
        version = self.db.get(TranscriptVersionModel, payload.transcript_version_id)
        if version is None:
            raise KeyError("Transcript version not found")
        transcript = self.db.get(TranscriptModel, version.transcript_id)
        if transcript is None:
            raise KeyError("Transcript not found")
        segments = self.db.execute(
            select(TranscriptSegmentModel)
            .where(TranscriptSegmentModel.transcript_id == transcript.id)
            .order_by(TranscriptSegmentModel.segment_index)
        ).scalars().all()

        export_id = _new_id()
        extension = _export_extension(payload.format.value)
        basename = _safe_export_basename(transcript.title)
        object_key = f"exports/{payload.workspace_id}/{export_id}-{basename}.{extension}"
        content = _render_export_content(payload.format.value, transcript, version, segments)
        settings = get_settings()
        export_path: Path = settings.upload_storage_path / object_key
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(content, encoding="utf-8")

        export = ExportModel(
            id=export_id,
            workspace_id=payload.workspace_id,
            transcript_version_id=payload.transcript_version_id,
            format=payload.format.value,
            object_key=object_key,
            created_at=_now(),
        )
        self.db.add(export)
        self.db.add(
            UsageLedgerModel(
                id=_new_id(),
                workspace_id=payload.workspace_id,
                job_id=None,
                usage_minutes=0.01,
                usage_type="export",
                created_at=_now(),
            )
        )
        self.db.commit()
        self.db.refresh(export)
        return ExportAsset(
            id=export.id,
            workspace_id=export.workspace_id,
            transcript_version_id=export.transcript_version_id,
            format=export.format,
            object_key=export.object_key,
            created_at=export.created_at,
        )

    def get_export(self, export_id: str) -> ExportAsset | None:
        export = self.db.get(ExportModel, export_id)
        if not export:
            return None
        return ExportAsset(
            id=export.id,
            workspace_id=export.workspace_id,
            transcript_version_id=export.transcript_version_id,
            format=export.format,
            object_key=export.object_key,
            created_at=export.created_at,
        )

    def export_download_filename(self, export_id: str) -> str:
        export = self.db.get(ExportModel, export_id)
        if export is None:
            raise KeyError("Export not found")
        version = self.db.get(TranscriptVersionModel, export.transcript_version_id)
        if version is None:
            raise KeyError("Transcript version not found")
        transcript = self.db.get(TranscriptModel, version.transcript_id)
        if transcript is None:
            raise KeyError("Transcript not found")
        extension = _export_extension(export.format)
        basename = _safe_export_basename(transcript.title)
        return f"{basename}.{extension}"

    @staticmethod
    def export_download_url(export_id: str) -> tuple[str, datetime]:
        expires_at = _now() + timedelta(minutes=30)
        return f"/v2/exports/{export_id}/file", expires_at

    def usage_summary(self, workspace_id: str) -> tuple[float, float, float]:
        used = self.db.execute(
            select(func.coalesce(func.sum(UsageLedgerModel.usage_minutes), 0.0)).where(
                UsageLedgerModel.workspace_id == workspace_id
            )
        ).scalar_one()
        quota = 120.0
        remaining = max(0.0, quota - float(used))
        return float(used), quota, remaining

    def create_abuse_report(self, payload: AbuseReportCreateRequest) -> AbuseReport:
        model = AbuseReportModel(
            id=_new_id(),
            workspace_id=payload.workspace_id,
            job_id=payload.job_id,
            reporter_email=payload.reporter_email,
            report_type=payload.report_type.value,
            description=payload.description,
            status=AbuseStatus.open.value,
            created_at=_now(),
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return AbuseReport(
            id=model.id,
            workspace_id=model.workspace_id,
            job_id=model.job_id,
            reporter_email=model.reporter_email,
            report_type=model.report_type,
            description=model.description,
            status=model.status,
            created_at=model.created_at,
        )

    def list_abuse_reports(self, status_filter: AbuseStatus | None) -> list[AbuseReport]:
        query = select(AbuseReportModel).order_by(desc(AbuseReportModel.created_at))
        if status_filter is not None:
            query = query.where(AbuseReportModel.status == status_filter.value)
        rows = self.db.execute(query).scalars().all()
        return [
            AbuseReport(
                id=row.id,
                workspace_id=row.workspace_id,
                job_id=row.job_id,
                reporter_email=row.reporter_email,
                report_type=row.report_type,
                description=row.description,
                status=row.status,
                created_at=row.created_at,
            )
            for row in rows
        ]
