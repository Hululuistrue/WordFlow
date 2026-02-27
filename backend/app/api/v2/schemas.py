from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class Workspace(BaseModel):
    id: str
    name: str
    owner_user_id: str
    created_at: datetime


class WorkspaceListResponse(BaseModel):
    items: list[Workspace]


class YouTubeConnectRequest(BaseModel):
    workspace_id: str


class YouTubeConnectResponse(BaseModel):
    authorization_url: str


class UploadInitRequest(BaseModel):
    workspace_id: str
    filename: str
    content_type: str
    size_bytes: int = Field(ge=1)


class UploadInitResponse(BaseModel):
    upload_id: str
    object_key: str
    presigned_url: str


class UploadCompleteResponse(BaseModel):
    source_asset_id: str


class UploadContentResponse(BaseModel):
    upload_id: str
    object_key: str
    stored_bytes: int


class JobSourceType(str, Enum):
    youtube_oauth = "youtube_oauth"
    upload = "upload"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    retrying = "retrying"
    canceled = "canceled"


class YouTubeClient(str, Enum):
    web = "web"
    web_ios = "web_ios"
    ios_web = "ios_web"
    tv_web = "tv_web"
    android_web = "android_web"
    android = "android"


class YouTubeMode(str, Enum):
    strict = "strict"
    compat = "compat"


class JobCreateRequest(BaseModel):
    workspace_id: str
    project_id: str | None = None
    source_type: JobSourceType
    source_asset_id: str | None = None
    youtube_video_id: str | None = None
    youtube_client: YouTubeClient = YouTubeClient.web
    youtube_mode: YouTubeMode = YouTubeMode.compat
    youtube_use_cookies: bool = False
    youtube_cookies_txt: str | None = None
    youtube_cookies_acknowledged: bool = False
    language_pref: str = "auto"
    with_timestamps: bool = True


class Job(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None = None
    source_type: JobSourceType
    youtube_client: YouTubeClient = YouTubeClient.web
    youtube_mode: YouTubeMode = YouTubeMode.compat
    youtube_use_cookies: bool = False
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    transcript_id: str | None = None


class JobListResponse(BaseModel):
    items: list[Job]
    next_cursor: str | None = None


class TranscriptSegment(BaseModel):
    index: int
    start_seconds: float
    end_seconds: float
    text: str


class TranscriptVersionStatus(str, Enum):
    draft = "draft"
    published = "published"


class TranscriptVersion(BaseModel):
    id: str
    transcript_id: str
    version_number: int
    edit_status: TranscriptVersionStatus
    edited_text: str
    editor_user_id: str
    created_at: datetime


class TranscriptDetail(BaseModel):
    id: str
    job_id: str
    title: str | None = None
    language: str | None = None
    source_label: str | None = None
    raw_text: str
    segments: list[TranscriptSegment]
    latest_version: TranscriptVersion


class TranscriptPatchRequest(BaseModel):
    edited_text: str


class ExportFormat(str, Enum):
    text = "text"
    txt = "txt"
    md = "md"
    srt = "srt"
    vtt = "vtt"


class ExportCreateRequest(BaseModel):
    workspace_id: str
    transcript_version_id: str
    format: ExportFormat


class ExportAsset(BaseModel):
    id: str
    workspace_id: str
    transcript_version_id: str
    format: ExportFormat
    object_key: str
    created_at: datetime


class ExportDownloadResponse(BaseModel):
    download_url: str
    expires_at: datetime


class UsageSummaryResponse(BaseModel):
    workspace_id: str
    used_minutes: float
    quota_minutes: float
    remaining_minutes: float


class AbuseReportType(str, Enum):
    copyright = "copyright"
    privacy = "privacy"
    illegal = "illegal"
    other = "other"


class AbuseStatus(str, Enum):
    open = "open"
    reviewing = "reviewing"
    resolved = "resolved"
    rejected = "rejected"


class AbuseReportCreateRequest(BaseModel):
    workspace_id: str | None = None
    job_id: str | None = None
    reporter_email: str | None = None
    report_type: AbuseReportType
    description: str = Field(min_length=10)


class AbuseReport(BaseModel):
    id: str
    workspace_id: str | None = None
    job_id: str | None = None
    reporter_email: str | None = None
    report_type: AbuseReportType
    description: str
    status: AbuseStatus
    created_at: datetime


class AbuseReportListResponse(BaseModel):
    items: list[AbuseReport]
