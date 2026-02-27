import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from sqlalchemy.orm import Session, sessionmaker

from app.api.v2.repository import JobProcessingContext, V2Repository
from app.api.v2.schemas import JobStatus, TranscriptSegment
from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.services.errors import SubtitleError
from app.services.upload_transcriber import UploadTranscriber
from app.services.youtube import YtDlpSubtitleFetcher


logger = logging.getLogger(__name__)
_STOP_SENTINEL = "__STOP__"
_YOUTUBE_ASR_FALLBACK_CODES = {"subtitle_unavailable", "subtitle_parse_failed", "subtitle_fetch_failed"}
_IMPORTANT_COOKIE_NAMES = {"sid", "hsid", "ssid", "apisid", "sapisid", "__secure-1psid", "__secure-3psid"}


def _summarize_cookies(text: str) -> dict[str, object]:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    domains: set[str] = set()
    names: set[str] = set()
    for line in lines:
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 7:
                domains.add(parts[0].lstrip(".").lower())
                names.add(parts[5].lower())
            continue
        for token in line.split(";"):
            part = token.strip()
            if "=" not in part:
                continue
            key, _ = part.split("=", 1)
            names.add(key.strip().lower())

    youtube_domain_count = sum(1 for item in domains if "youtube.com" in item)
    google_domain_count = sum(1 for item in domains if "google.com" in item)
    important_present = sorted(name for name in _IMPORTANT_COOKIE_NAMES if name in names)
    return {
        "line_count": len(lines),
        "domain_count": len(domains),
        "youtube_domain_count": youtube_domain_count,
        "google_domain_count": google_domain_count,
        "cookie_name_count": len(names),
        "important_cookie_count": len(important_present),
        "important_cookie_names": important_present,
    }


class V2JobQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        settings: Settings | None = None,
        subtitle_fetcher: YtDlpSubtitleFetcher | None = None,
        upload_transcriber: UploadTranscriber | None = None,
    ):
        self._settings = settings or get_settings()
        self._session_factory = session_factory or get_session_factory()
        self._subtitle_fetcher = subtitle_fetcher or YtDlpSubtitleFetcher(settings=self._settings)
        self._upload_transcriber = upload_transcriber or UploadTranscriber(settings=self._settings)
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._worker_loop(), name="v2-job-worker")
        logger.info("v2_job_queue_started")

    async def stop(self) -> None:
        if not self._worker_task:
            return
        await self._queue.put(_STOP_SENTINEL)
        await self._worker_task
        self._worker_task = None
        logger.info("v2_job_queue_stopped")

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(job_id)
        logger.info("v2_job_enqueued job_id=%s", job_id)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                if job_id == _STOP_SENTINEL:
                    return
                await self._handle_job(job_id)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("v2_job_worker_crash job_id=%s error=%s", job_id, exc)
            finally:
                self._queue.task_done()

    async def _handle_job(self, job_id: str) -> None:
        with self._session_factory() as db:
            repo = V2Repository(db)
            job = repo.mark_job_running(job_id)
            if job.status == JobStatus.canceled:
                logger.info("v2_job_skipped_canceled job_id=%s", job_id)
                return
            context = repo.get_job_processing_context(job_id)
            if context is None:
                repo.mark_job_failed(job_id, error_code="job_not_found", error_message="Job disappeared during processing.")
                return

        await asyncio.sleep(0.2)

        try:
            title, source_label, language, raw_text, segments, engine = await asyncio.to_thread(
                self._process_job_context,
                context,
            )
            with self._session_factory() as db:
                repo = V2Repository(db)
                job = repo.mark_job_success(
                    job_id=job_id,
                    editor_user_id="system-worker",
                    title=title,
                    source_label=source_label,
                    language=language,
                    raw_text=raw_text,
                    segments=segments,
                    engine=engine,
                )
                logger.info("v2_job_succeeded job_id=%s status=%s", job_id, job.status)
        except SubtitleError as exc:
            with self._session_factory() as db:
                repo = V2Repository(db)
                repo.mark_job_failed(job_id, error_code=exc.code, error_message=exc.user_message)
            logger.warning(
                "v2_job_failed job_id=%s code=%s error=%s raw=%s",
                job_id,
                exc.code,
                exc.user_message,
                exc.raw_message,
            )
        except Exception as exc:
            with self._session_factory() as db:
                repo = V2Repository(db)
                repo.mark_job_failed(job_id, error_code="worker_error", error_message=str(exc))
            logger.warning("v2_job_failed job_id=%s error=%s", job_id, exc)

    def _process_job_context(
        self,
        context: JobProcessingContext,
    ) -> tuple[str | None, str, str | None, str, list[TranscriptSegment], str]:
        if context.source_type == "youtube_oauth":
            if not context.youtube_video_id:
                raise ValueError("youtube_video_id is required for youtube_oauth jobs")
            url = f"https://www.youtube.com/watch?v={context.youtube_video_id}"
            root = self._settings.temp_path
            root.mkdir(parents=True, exist_ok=True)
            youtube_tmp_dir = Path(tempfile.mkdtemp(prefix="yt_job_", dir=str(root)))
            cookies_file: Path | None = None
            try:
                if context.youtube_use_cookies and context.youtube_cookies_txt:
                    diagnostics = _summarize_cookies(context.youtube_cookies_txt)
                    logger.info("v2_job_youtube_cookies_diagnostics job_id=%s %s", context.job_id, diagnostics)
                    cookies_file = youtube_tmp_dir / "cookies.txt"
                    cookies_file.write_text(context.youtube_cookies_txt, encoding="utf-8")

                try:
                    result = self._subtitle_fetcher.fetch_subtitles(
                        url=url,
                        language_pref=context.language_pref,  # type: ignore[arg-type]
                        with_timestamps=context.with_timestamps,
                        cookies_file=cookies_file,
                        youtube_client=context.youtube_client,
                        youtube_mode=context.youtube_mode,
                    )
                    segments = [
                        TranscriptSegment(
                            index=index,
                            start_seconds=seg.start,
                            end_seconds=seg.end,
                            text=seg.text,
                        )
                        for index, seg in enumerate(result.segments)
                    ]
                    return result.title, result.source, result.language, result.result_text, segments, "yt-dlp"
                except SubtitleError as subtitle_error:
                    if context.youtube_use_cookies and subtitle_error.code == "bot_or_rate_limited":
                        raise SubtitleError(
                            "cookies_invalid_or_blocked",
                            "Uploaded cookies were accepted, but YouTube still blocked the request. Cookies may be expired, incomplete, or this IP is being challenged.",
                            subtitle_error.raw_message,
                        ) from subtitle_error
                    if subtitle_error.code not in _YOUTUBE_ASR_FALLBACK_CODES:
                        raise
                    logger.info(
                        "v2_job_youtube_subtitle_fallback_to_asr job_id=%s code=%s",
                        context.job_id,
                        subtitle_error.code,
                    )
                    try:
                        return self._transcribe_youtube_by_asr(context=context, url=url, cookies_file=cookies_file)
                    except SubtitleError as asr_error:
                        if context.youtube_use_cookies and asr_error.code == "bot_or_rate_limited":
                            raise SubtitleError(
                                "cookies_invalid_or_blocked",
                                "Uploaded cookies were accepted, but YouTube still blocked the request. Cookies may be expired, incomplete, or this IP is being challenged.",
                                asr_error.raw_message,
                            ) from asr_error
                        raise
            finally:
                shutil.rmtree(youtube_tmp_dir, ignore_errors=True)

        if context.source_type == "upload":
            if not context.upload_object_key:
                raise SubtitleError("upload_file_missing", "Uploaded file is missing. Please upload file content first.")
            media_path: Path = self._settings.upload_storage_path / context.upload_object_key
            language, raw_text, segments, engine = self._upload_transcriber.transcribe(
                media_path=media_path,
                language_pref=context.language_pref,
                with_timestamps=context.with_timestamps,
            )
            title = Path(context.upload_filename or context.upload_object_key or "upload").stem
            return title, "upload_asr", language, raw_text, segments, engine

        raise ValueError(f"Unsupported source_type: {context.source_type}")

    def _transcribe_youtube_by_asr(
        self,
        context: JobProcessingContext,
        url: str,
        cookies_file: Path | None = None,
    ) -> tuple[str | None, str, str | None, str, list[TranscriptSegment], str]:
        root = self._settings.temp_path
        root.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="yt_audio_", dir=str(root)))
        try:
            title = self._subtitle_fetcher.fetch_title(
                url=url,
                cookies_file=cookies_file,
                youtube_client=context.youtube_client,
                youtube_mode=context.youtube_mode,
            )
            media_path = self._subtitle_fetcher.download_audio(
                url=url,
                output_dir=tmp_dir,
                cookies_file=cookies_file,
                youtube_client=context.youtube_client,
                youtube_mode=context.youtube_mode,
            )
            language, raw_text, segments, engine = self._upload_transcriber.transcribe(
                media_path=media_path,
                language_pref=context.language_pref,
                with_timestamps=context.with_timestamps,
            )
            return title, "youtube_asr_fallback", language, raw_text, segments, f"{engine}+yt-dlp"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
