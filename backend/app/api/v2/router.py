from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.v2.repository import V2Repository
from app.api.v2.schemas import (
    AbuseReport,
    AbuseReportCreateRequest,
    AbuseReportListResponse,
    AbuseStatus,
    AuthTokenResponse,
    ExportAsset,
    ExportCreateRequest,
    ExportDownloadResponse,
    Job,
    JobCreateRequest,
    JobListResponse,
    JobStatus,
    TranscriptDetail,
    TranscriptPatchRequest,
    TranscriptVersion,
    UploadCompleteResponse,
    UploadContentResponse,
    UploadInitRequest,
    UploadInitResponse,
    UsageSummaryResponse,
    Workspace,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    YouTubeClient,
    YouTubeMode,
    YouTubeConnectRequest,
    YouTubeConnectResponse,
)
from app.core.config import get_settings
from app.db.session import get_db_session

router = APIRouter(prefix="/v2", tags=["v2"])


def get_repository(db: Session = Depends(get_db_session)) -> V2Repository:
    return V2Repository(db)


def _default_user_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


def _looks_like_netscape_cookies(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return False
    return any(line.count("\t") >= 6 for line in lines)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _to_expiry_epoch(value: object | None, session: bool) -> int:
    if session:
        return 0
    if value is None:
        return 0

    numeric: float | None = None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                numeric = float(raw)
            except ValueError:
                numeric = None

    if numeric is None:
        return 0
    if numeric < 0:
        return 0
    if numeric > 10_000_000_000:
        numeric = numeric / 1000.0
    return int(numeric)


def _normalize_domain(raw_domain: str, host_only: bool = False) -> tuple[str, bool] | None:
    domain_text = raw_domain.strip()
    if not domain_text:
        return None

    include_subdomains = domain_text.startswith(".") and not host_only
    clean = domain_text.lstrip(".")

    if "://" in clean:
        parsed = urlparse(clean)
        clean = parsed.hostname or ""
    else:
        clean = clean.split("/")[0]

    clean = clean.split(":")[0].strip().lower()
    if not clean:
        return None
    if clean.startswith("www."):
        clean = clean[4:]

    final_domain = f".{clean}" if include_subdomains else clean
    return final_domain, include_subdomains


def _cookie_header_to_netscape_cookies(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None

    attr_keys = {
        "path",
        "domain",
        "expires",
        "max-age",
        "samesite",
        "httponly",
        "secure",
        "priority",
        "partitioned",
    }
    default_domain = ".youtube.com"
    default_include_subdomains = True
    default_path = "/"
    default_secure = True
    default_expiry = 2147483647

    pairs: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("cookie:"):
            line = line.split(":", 1)[1].strip()
        if lower.startswith("set-cookie:"):
            line = line.split(":", 1)[1].strip()

        for token in line.split(";"):
            part = token.strip()
            if not part or "=" not in part:
                continue
            key, cookie_value = part.split("=", 1)
            key = key.strip()
            cookie_value = cookie_value.strip()
            if not key:
                continue
            if key.lower() in attr_keys:
                continue
            if cookie_value.startswith('"') and cookie_value.endswith('"') and len(cookie_value) >= 2:
                cookie_value = cookie_value[1:-1]
            pairs.append((key, cookie_value))

    if not pairs:
        return None

    lines = [
        "\t".join(
            [
                default_domain,
                "TRUE" if default_include_subdomains else "FALSE",
                default_path,
                "TRUE" if default_secure else "FALSE",
                str(default_expiry),
                key,
                cookie_value,
            ]
        )
        for key, cookie_value in pairs
    ]
    return "# Netscape HTTP Cookie File\n" + "\n".join(lines) + "\n"


def _json_to_netscape_cookies(value: str) -> str | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None

    rows: list[dict] | None = None
    if isinstance(parsed, list):
        rows = [item for item in parsed if isinstance(item, dict)]
    elif isinstance(parsed, dict):
        cookies = parsed.get("cookies")
        if isinstance(cookies, list):
            rows = [item for item in cookies if isinstance(item, dict)]

    if not rows:
        return None

    lines: list[str] = []
    for row in rows:
        name = str(row.get("name") or row.get("key") or "").strip()
        if not name:
            continue
        cookie_value = str(row.get("value") or "")

        raw_domain_value = row.get("domain") or row.get("host") or row.get("url") or ""
        raw_domain = str(raw_domain_value).strip()
        host_only = _as_bool(row.get("hostOnly"))
        normalized = _normalize_domain(raw_domain, host_only=host_only)
        if not normalized:
            continue
        domain, include_subdomains = normalized

        path = str(row.get("path") or "/").strip() or "/"
        secure = _as_bool(row.get("secure") if "secure" in row else row.get("isSecure"))
        session = _as_bool(row.get("session"))
        expiry_raw = (
            row.get("expirationDate")
            if "expirationDate" in row
            else row.get("expires")
            if "expires" in row
            else row.get("expiry")
        )
        expiry = _to_expiry_epoch(expiry_raw, session=session)

        lines.append(
            "\t".join(
                [
                    domain,
                    "TRUE" if include_subdomains else "FALSE",
                    path,
                    "TRUE" if secure else "FALSE",
                    str(expiry),
                    name,
                    cookie_value,
                ]
            )
        )

    if not lines:
        return None
    return "# Netscape HTTP Cookie File\n" + "\n".join(lines) + "\n"


def _normalize_cookies_text(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if _looks_like_netscape_cookies(text):
        return text + ("\n" if not text.endswith("\n") else "")
    as_json = _json_to_netscape_cookies(text)
    if as_json:
        return as_json
    return _cookie_header_to_netscape_cookies(text)


@router.post("/auth/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
async def register_user(_: dict) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=f"access-{uuid4()}",
        refresh_token=f"refresh-{uuid4()}",
    )


@router.post("/auth/login", response_model=AuthTokenResponse, tags=["Auth"])
async def login_user(_: dict) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=f"access-{uuid4()}",
        refresh_token=f"refresh-{uuid4()}",
    )


@router.post("/workspaces", response_model=Workspace, status_code=status.HTTP_201_CREATED, tags=["Auth"])
async def create_workspace(payload: WorkspaceCreateRequest, repo: V2Repository = Depends(get_repository)) -> Workspace:
    return repo.create_workspace(name=payload.name, owner_user_id=_default_user_id())


@router.get("/workspaces", response_model=WorkspaceListResponse, tags=["Auth"])
async def list_workspaces(repo: V2Repository = Depends(get_repository)) -> WorkspaceListResponse:
    return WorkspaceListResponse(items=repo.list_workspaces())


@router.post("/integrations/youtube/connect", response_model=YouTubeConnectResponse, tags=["Integrations"])
async def youtube_connect(payload: YouTubeConnectRequest, repo: V2Repository = Depends(get_repository)) -> YouTubeConnectResponse:
    if not repo.workspace_exists(payload.workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    oauth_state = str(uuid4())
    return YouTubeConnectResponse(
        authorization_url=f"https://accounts.google.com/o/oauth2/v2/auth?state={oauth_state}"
    )


@router.get(
    "/integrations/youtube/callback",
    status_code=status.HTTP_302_FOUND,
    tags=["Integrations"],
)
async def youtube_callback(code: str, state: str) -> RedirectResponse:
    redirect_url = f"https://app.transcriptpro.example.com/integrations/youtube?code={code}&state={state}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.post("/uploads/init", response_model=UploadInitResponse, tags=["Uploads"])
async def init_upload(payload: UploadInitRequest, repo: V2Repository = Depends(get_repository)) -> UploadInitResponse:
    if not repo.workspace_exists(payload.workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    upload = repo.create_upload(
        workspace_id=payload.workspace_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
    )
    return UploadInitResponse(
        upload_id=upload.id,
        object_key=upload.object_key,
        presigned_url=f"/v2/uploads/{upload.id}/content",
    )


@router.post("/uploads/{upload_id}/content", response_model=UploadContentResponse, tags=["Uploads"])
async def upload_content(
    upload_id: str,
    file: UploadFile = File(...),
    repo: V2Repository = Depends(get_repository),
) -> UploadContentResponse:
    upload = repo.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    settings = get_settings()
    storage_root = settings.upload_storage_path
    storage_root.mkdir(parents=True, exist_ok=True)

    safe_name = (file.filename or upload.filename or "upload.bin").replace("\\", "_").replace("/", "_")
    relative_key = Path("uploads") / upload.workspace_id / upload.id / safe_name
    target_path = storage_root / relative_key
    target_path.parent.mkdir(parents=True, exist_ok=True)

    content = await file.read()
    target_path.write_bytes(content)
    updated = repo.update_upload_object_key(upload_id=upload_id, object_key=str(relative_key), size_bytes=len(content))
    return UploadContentResponse(upload_id=updated.id, object_key=updated.object_key, stored_bytes=len(content))


@router.post("/uploads/{upload_id}/complete", response_model=UploadCompleteResponse, tags=["Uploads"])
async def complete_upload(upload_id: str, repo: V2Repository = Depends(get_repository)) -> UploadCompleteResponse:
    if not repo.get_upload(upload_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    source_asset_id = repo.complete_upload(upload_id)
    return UploadCompleteResponse(source_asset_id=source_asset_id)


@router.post("/jobs", response_model=Job, status_code=status.HTTP_201_CREATED, tags=["Jobs"])
async def create_job(
    payload: JobCreateRequest,
    request: Request,
    repo: V2Repository = Depends(get_repository),
) -> Job:
    settings = getattr(request.app.state, "settings", get_settings())
    if not repo.workspace_exists(payload.workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if payload.source_type.value == "upload" and not payload.source_asset_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_asset_id is required for upload jobs")
    if payload.source_type.value == "youtube_oauth" and not payload.youtube_video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="youtube_video_id is required for youtube_oauth jobs",
        )
    if payload.source_type.value == "upload" and payload.source_asset_id and not repo.source_asset_exists(payload.source_asset_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source asset not found")
    if payload.source_type.value != "youtube_oauth":
        payload.youtube_client = YouTubeClient.web
        payload.youtube_mode = YouTubeMode.strict
        payload.youtube_use_cookies = False
        payload.youtube_cookies_txt = None
        payload.youtube_cookies_acknowledged = False
    elif payload.youtube_use_cookies:
        if not settings.allow_user_supplied_cookies:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User supplied cookies are disabled by server policy.",
            )
        if not payload.youtube_cookies_acknowledged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please acknowledge cookie security risks before using this option.",
            )
        cookies_text = (payload.youtube_cookies_txt or "").strip()
        if not cookies_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="youtube_cookies_txt is required")
        if len(cookies_text) > settings.youtube_cookies_max_chars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"youtube_cookies_txt exceeds max length ({settings.youtube_cookies_max_chars}).",
            )
        normalized_cookies = _normalize_cookies_text(cookies_text)
        if not normalized_cookies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cookies format. Please provide Netscape cookies.txt, JSON exported cookies, or Cookie header text.",
            )
        payload.youtube_cookies_txt = normalized_cookies
    else:
        payload.youtube_cookies_txt = None

    job = repo.create_job(payload=payload, created_by=_default_user_id())
    queue = getattr(request.app.state, "v2_job_queue", None)
    if queue is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job queue unavailable")
    await queue.enqueue(job.id)
    return job


@router.get("/jobs", response_model=JobListResponse, tags=["Jobs"])
async def list_jobs(
    workspace_id: str = Query(...),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=200),
    cursor: str | None = Query(default=None),
    repo: V2Repository = Depends(get_repository),
) -> JobListResponse:
    if not repo.workspace_exists(workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    items, next_cursor = repo.list_jobs(workspace_id=workspace_id, status_filter=status_filter, limit=limit, cursor=cursor)
    return JobListResponse(items=items, next_cursor=next_cursor)


@router.get("/jobs/{job_id}", response_model=Job, tags=["Jobs"])
async def get_job(job_id: str, repo: V2Repository = Depends(get_repository)) -> Job:
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/retry", response_model=Job, status_code=status.HTTP_202_ACCEPTED, tags=["Jobs"])
async def retry_job(job_id: str, request: Request, repo: V2Repository = Depends(get_repository)) -> Job:
    try:
        job = repo.retry_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
    queue = getattr(request.app.state, "v2_job_queue", None)
    if queue is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job queue unavailable")
    await queue.enqueue(job.id)
    return job


@router.post("/jobs/{job_id}/cancel", response_model=Job, status_code=status.HTTP_202_ACCEPTED, tags=["Jobs"])
async def cancel_job(job_id: str, repo: V2Repository = Depends(get_repository)) -> Job:
    try:
        return repo.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc


@router.get("/transcripts/{transcript_id}", response_model=TranscriptDetail, tags=["Transcripts"])
async def get_transcript(transcript_id: str, repo: V2Repository = Depends(get_repository)) -> TranscriptDetail:
    transcript = repo.get_transcript(transcript_id)
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
    return transcript


@router.patch("/transcripts/{transcript_id}", response_model=TranscriptVersion, tags=["Transcripts"])
async def patch_transcript(
    transcript_id: str,
    payload: TranscriptPatchRequest,
    repo: V2Repository = Depends(get_repository),
) -> TranscriptVersion:
    try:
        return repo.update_transcript(
            transcript_id=transcript_id,
            payload=payload,
            editor_user_id=_default_user_id(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found") from exc


@router.post(
    "/transcripts/{transcript_id}/versions/{version_id}/publish",
    response_model=TranscriptVersion,
    tags=["Transcripts"],
)
async def publish_transcript_version(
    transcript_id: str,
    version_id: str,
    repo: V2Repository = Depends(get_repository),
) -> TranscriptVersion:
    transcript = repo.get_transcript(transcript_id)
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
    if not repo.transcript_version_exists(version_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    try:
        return repo.publish_version(transcript_id=transcript_id, version_id=version_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/exports", response_model=ExportAsset, status_code=status.HTTP_201_CREATED, tags=["Exports"])
async def create_export(payload: ExportCreateRequest, repo: V2Repository = Depends(get_repository)) -> ExportAsset:
    if not repo.workspace_exists(payload.workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if not repo.transcript_version_exists(payload.transcript_version_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript version not found")
    return repo.create_export(payload)


@router.get("/exports/{export_id}/download", response_model=ExportDownloadResponse, tags=["Exports"])
async def download_export(export_id: str, repo: V2Repository = Depends(get_repository)) -> ExportDownloadResponse:
    if repo.get_export(export_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    url, expires_at = repo.export_download_url(export_id)
    return ExportDownloadResponse(download_url=url, expires_at=expires_at)


@router.get("/exports/{export_id}/file", tags=["Exports"])
async def download_export_file(export_id: str, repo: V2Repository = Depends(get_repository)) -> FileResponse:
    export = repo.get_export(export_id)
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")

    settings = get_settings()
    file_path = settings.upload_storage_path / export.object_key
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found")
    try:
        download_name = repo.export_download_filename(export_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(path=file_path, filename=download_name, media_type="application/octet-stream")


@router.get("/usage/summary", response_model=UsageSummaryResponse, tags=["Usage"])
async def usage_summary(
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
    repo: V2Repository = Depends(get_repository),
) -> UsageSummaryResponse:
    if period_end <= period_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period_end must be later than period_start")
    if not repo.workspace_exists(workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    used, quota, remaining = repo.usage_summary(workspace_id)
    return UsageSummaryResponse(
        workspace_id=workspace_id,
        used_minutes=used,
        quota_minutes=quota,
        remaining_minutes=remaining,
    )


@router.post("/abuse-reports", response_model=AbuseReport, status_code=status.HTTP_201_CREATED, tags=["Abuse"])
async def create_abuse_report(payload: AbuseReportCreateRequest, repo: V2Repository = Depends(get_repository)) -> AbuseReport:
    return repo.create_abuse_report(payload)


@router.get("/abuse-reports", response_model=AbuseReportListResponse, tags=["Abuse"])
async def list_abuse_reports(
    status_filter: AbuseStatus | None = Query(default=None, alias="status"),
    repo: V2Repository = Depends(get_repository),
) -> AbuseReportListResponse:
    return AbuseReportListResponse(items=repo.list_abuse_reports(status_filter))
