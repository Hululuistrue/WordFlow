from pathlib import Path
import tempfile

import pytest

from app.api.v2.repository import JobProcessingContext
from app.api.v2.schemas import TranscriptSegment
from app.core.config import Settings
from app.services.errors import SubtitleError
from app.services.v2_job_queue import V2JobQueue


class StubSubtitleFetcher:
    def __init__(self, error: SubtitleError):
        self._error = error
        self.download_called = False

    def fetch_title(
        self,
        url: str,
        cookies_file: Path | None = None,
        youtube_client: str | None = None,
        youtube_mode: str = "strict",
    ) -> str | None:
        return "Demo Video"

    def fetch_subtitles(  # noqa: ANN201
        self,
        url: str,
        language_pref: str,
        with_timestamps: bool,
        cookies_file: Path | None = None,
        youtube_client: str | None = None,
        youtube_mode: str = "strict",
    ):
        raise self._error

    def download_audio(
        self,
        url: str,
        output_dir: Path,
        cookies_file: Path | None = None,
        youtube_client: str | None = None,
        youtube_mode: str = "strict",
    ) -> Path:
        self.download_called = True
        return output_dir / "audio.m4a"


class StubUploadTranscriber:
    def __init__(self):
        self.called = False

    def transcribe(self, media_path: Path, language_pref: str, with_timestamps: bool):  # noqa: ANN201
        self.called = True
        return (
            "en",
            "[0.000-1.000] hello",
            [
                TranscriptSegment(
                    index=0,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    text="hello",
                )
            ],
            "faster-whisper:base",
        )


def _youtube_context() -> JobProcessingContext:
    return JobProcessingContext(
        job_id="job-1",
        workspace_id="ws-1",
        source_type="youtube_oauth",
        source_asset_id=None,
        upload_object_key=None,
        upload_filename=None,
        youtube_video_id="dQw4w9WgXcQ",
        youtube_client="web",
        youtube_mode="strict",
        youtube_use_cookies=False,
        youtube_cookies_txt=None,
        language_pref="auto",
        with_timestamps=True,
    )


def test_youtube_job_falls_back_to_asr_when_subtitle_unavailable() -> None:
    fetcher = StubSubtitleFetcher(
        SubtitleError("subtitle_unavailable", "No subtitles were found for this video."),
    )
    transcriber = StubUploadTranscriber()
    queue = V2JobQueue(
        settings=Settings(temp_dir=tempfile.gettempdir()),
        subtitle_fetcher=fetcher,  # type: ignore[arg-type]
        upload_transcriber=transcriber,  # type: ignore[arg-type]
    )

    title, source, language, raw_text, segments, engine = queue._process_job_context(_youtube_context())

    assert title == "Demo Video"
    assert source == "youtube_asr_fallback"
    assert language == "en"
    assert raw_text == "[0.000-1.000] hello"
    assert len(segments) == 1
    assert engine == "faster-whisper:base+yt-dlp"
    assert fetcher.download_called is True
    assert transcriber.called is True


def test_youtube_job_does_not_fallback_for_bot_blocking_error() -> None:
    fetcher = StubSubtitleFetcher(
        SubtitleError("bot_or_rate_limited", "YouTube is blocking requests (bot check/rate limit)."),
    )
    transcriber = StubUploadTranscriber()
    queue = V2JobQueue(
        settings=Settings(temp_dir=tempfile.gettempdir()),
        subtitle_fetcher=fetcher,  # type: ignore[arg-type]
        upload_transcriber=transcriber,  # type: ignore[arg-type]
    )

    with pytest.raises(SubtitleError) as exc_info:
        queue._process_job_context(_youtube_context())

    assert exc_info.value.code == "bot_or_rate_limited"
    assert fetcher.download_called is False
    assert transcriber.called is False


def test_youtube_job_with_user_cookies_surfaces_clearer_blocked_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher = StubSubtitleFetcher(
        SubtitleError("bot_or_rate_limited", "YouTube is blocking requests (bot check/rate limit)."),
    )
    transcriber = StubUploadTranscriber()
    queue = V2JobQueue(
        settings=Settings(temp_dir=tempfile.gettempdir()),
        subtitle_fetcher=fetcher,  # type: ignore[arg-type]
        upload_transcriber=transcriber,  # type: ignore[arg-type]
    )
    context = _youtube_context()
    context.youtube_use_cookies = True
    context.youtube_cookies_txt = ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tvalue"
    monkeypatch.setattr(Path, "write_text", lambda self, data, encoding=None: len(data))

    with pytest.raises(SubtitleError) as exc_info:
        queue._process_job_context(context)

    assert exc_info.value.code == "cookies_invalid_or_blocked"
    assert "accepted" in exc_info.value.user_message.lower()
