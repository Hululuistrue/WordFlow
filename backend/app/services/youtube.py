import logging
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.models.task import LanguagePref, TranscriptSegment
from app.services.errors import SubtitleError, is_subtitle_absence_error, map_yt_dlp_error
from app.services.subtitle_parser import parse_vtt, segments_to_text

logger = logging.getLogger(__name__)

_YOUTUBE_CLIENT_TO_EXTRACTOR_ARGS = {
    "web": "youtube:player_client=web",
    "web_ios": "youtube:player_client=web,ios",
    "ios_web": "youtube:player_client=ios,web",
    "tv_web": "youtube:player_client=tv,web",
    "android_web": "youtube:player_client=android,web",
    "android": "youtube:player_client=android",
}

_COMPAT_COOKIE_CLIENT_ORDER = ["web", "web_ios", "ios_web"]
_COMPAT_NO_COOKIE_CLIENT_ORDER = ["web", "web_ios", "ios_web", "tv_web", "android_web"]


@dataclass
class FetchResult:
    title: str | None
    source: str
    language: str | None
    result_text: str
    segments: list[TranscriptSegment]


def _language_patterns(language_pref: LanguagePref) -> str:
    if language_pref == "zh":
        return "zh.*,zh-Hans,zh-Hant,zh-CN,zh-TW"
    if language_pref == "en":
        return "en.*,en-US,en-GB"
    return "all,-live_chat"


def _language_fallback_order(language_pref: LanguagePref) -> list[LanguagePref]:
    if language_pref == "auto":
        return ["auto"]
    return [language_pref, "auto"]


def _detect_language_from_filename(path: Path) -> str | None:
    # Expected pattern: subtitle.<lang>.vtt
    parts = path.name.split(".")
    if len(parts) >= 3:
        return parts[-2]
    return None


def _score_file(path: Path, language_pref: LanguagePref) -> int:
    name = path.name.lower()
    if language_pref == "zh":
        return 100 if ".zh" in name else 10
    if language_pref == "en":
        return 100 if ".en" in name else 10
    if ".zh" in name:
        return 100
    if ".en" in name:
        return 90
    return 10


def _parse_browser_candidates(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _error_excerpt(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    line = text.splitlines()[0].strip()
    return line[:300]


def _normalize_client_key(youtube_client: str | None, has_cookies: bool) -> str:
    key = (youtube_client or "web").strip()
    if key not in _YOUTUBE_CLIENT_TO_EXTRACTOR_ARGS:
        return "web"
    if has_cookies and key in {"android", "android_web"}:
        # Android clients do not work well with cookie-based auth.
        return "web"
    return key


def _extractor_arg_candidates(
    settings: Settings,
    has_cookies: bool = False,
    youtube_client: str | None = None,
    youtube_mode: str = "strict",
) -> list[str]:
    selected = _normalize_client_key(youtube_client, has_cookies=has_cookies)
    if youtube_mode == "compat":
        order = _COMPAT_COOKIE_CLIENT_ORDER if has_cookies else _COMPAT_NO_COOKIE_CLIENT_ORDER
        keys: list[str] = [selected]
        for item in order:
            if item not in keys:
                keys.append(item)
            if len(keys) >= 3:
                break
        return [_YOUTUBE_CLIENT_TO_EXTRACTOR_ARGS[item] for item in keys]

    if youtube_client:
        return [_YOUTUBE_CLIENT_TO_EXTRACTOR_ARGS[selected]]

    configured = settings.ytdlp_extractor_args.strip()
    if configured:
        return [configured]
    return [_YOUTUBE_CLIENT_TO_EXTRACTOR_ARGS["web"]]


def _auth_candidates(settings: Settings, user_cookies_file: Path | None = None) -> list[list[str]]:
    if user_cookies_file is not None:
        return [["--cookies", str(user_cookies_file)]]

    candidates: list[list[str]] = []
    if settings.ytdlp_cookies_file.strip():
        candidates.append(["--cookies", settings.ytdlp_cookies_file.strip()])

    for browser in _parse_browser_candidates(settings.ytdlp_cookies_from_browser):
        candidates.append(["--cookies-from-browser", browser])

    # Last fallback: no authentication arguments.
    candidates.append([])
    return candidates


class YtDlpSubtitleFetcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_subtitles(
        self,
        url: str,
        language_pref: LanguagePref = "auto",
        with_timestamps: bool = True,
        cookies_file: Path | None = None,
        youtube_client: str | None = None,
        youtube_mode: str = "strict",
    ) -> FetchResult:
        root = self.settings.temp_path
        root.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="yt_task_", dir=str(root)))

        try:
            title = self.fetch_title(
                url=url,
                cookies_file=cookies_file,
                youtube_client=youtube_client,
                youtube_mode=youtube_mode,
            )
            last_parse_error: SubtitleError | None = None
            for candidate_pref in _language_fallback_order(language_pref):
                for auto in (False, True):
                    subtitle_file = self._download_subtitles(
                        url,
                        candidate_pref,
                        tmp_dir,
                        auto=auto,
                        cookies_file=cookies_file,
                        youtube_client=youtube_client,
                        youtube_mode=youtube_mode,
                    )
                    if subtitle_file is None:
                        continue

                    source = "subtitle_auto" if auto else "subtitle_manual"
                    if candidate_pref == "auto" and language_pref != "auto":
                        source = f"{source}_all_lang"

                    raw_text = subtitle_file.read_text(encoding="utf-8", errors="ignore")
                    segments = parse_vtt(raw_text)
                    if not segments:
                        last_parse_error = SubtitleError(
                            "subtitle_parse_failed",
                            "Subtitles were found but could not be parsed.",
                            None,
                        )
                        continue

                    result_text = segments_to_text(segments, with_timestamps=with_timestamps)
                    language = _detect_language_from_filename(subtitle_file)
                    return FetchResult(
                        title=title,
                        source=source,
                        language=language,
                        result_text=result_text,
                        segments=segments,
                    )

            if last_parse_error is not None:
                raise last_parse_error
            raise SubtitleError(
                "subtitle_unavailable",
                "No subtitles were found for this video.",
                None,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def fetch_title(
        self,
        url: str,
        cookies_file: Path | None = None,
        youtube_client: str | None = None,
        youtube_mode: str = "strict",
    ) -> str | None:
        extractor_args = _extractor_arg_candidates(
            self.settings,
            has_cookies=cookies_file is not None,
            youtube_client=youtube_client,
            youtube_mode=youtube_mode,
        )[0]
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-config-locations",
            "--no-playlist",
            "--skip-download",
            "--print",
            "%(title)s",
        ]
        if self.settings.ytdlp_js_runtimes.strip():
            command.extend(["--js-runtimes", self.settings.ytdlp_js_runtimes.strip()])
        if self.settings.ytdlp_remote_components.strip():
            command.extend(["--remote-components", self.settings.ytdlp_remote_components.strip()])
        if extractor_args:
            command.extend(["--extractor-args", extractor_args])
        command.append(url)

        for auth_args in _auth_candidates(self.settings, user_cookies_file=cookies_file):
            current = [*command]
            if auth_args:
                current = current[:-1] + auth_args + [current[-1]]
            try:
                proc = subprocess.run(
                    current,
                    capture_output=True,
                    text=True,
                    timeout=min(20, self.settings.subtitle_fetch_timeout_seconds),
                    check=False,
                )
            except Exception:
                continue
            if proc.returncode == 0:
                lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
                if lines:
                    return lines[-1][:255]
        return None

    def _download_subtitles(
        self,
        url: str,
        language_pref: LanguagePref,
        output_dir: Path,
        auto: bool,
        cookies_file: Path | None = None,
        youtube_client: str | None = None,
        youtube_mode: str = "strict",
    ) -> Path | None:
        output_tpl = str(output_dir / "subtitle.%(language)s.%(ext)s")
        last_error: SubtitleError | None = None
        for extractor_args in _extractor_arg_candidates(
            self.settings,
            has_cookies=cookies_file is not None,
            youtube_client=youtube_client,
            youtube_mode=youtube_mode,
        ):
            base_command = [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-config-locations",
                "--no-playlist",
                "--skip-download",
                "--sub-format",
                "vtt",
                "--sub-langs",
                _language_patterns(language_pref),
                "--output",
                output_tpl,
            ]
            if self.settings.ytdlp_js_runtimes.strip():
                base_command.extend(["--js-runtimes", self.settings.ytdlp_js_runtimes.strip()])
            if self.settings.ytdlp_remote_components.strip():
                base_command.extend(["--remote-components", self.settings.ytdlp_remote_components.strip()])
            if extractor_args:
                base_command.extend(["--extractor-args", extractor_args])
            if auto:
                base_command.extend(["--write-auto-subs", "--no-write-subs"])
            else:
                base_command.extend(["--write-subs", "--no-write-auto-subs"])
            base_command.append(url)

            logger.info(
                "yt_subtitle_attempt auto=%s lang_pref=%s extractor_args=%s has_user_cookies=%s mode=%s",
                auto,
                language_pref,
                extractor_args,
                cookies_file is not None,
                youtube_mode,
            )
            next_extractor = False
            for auth_args in _auth_candidates(self.settings, user_cookies_file=cookies_file):
                command = [*base_command]
                if auth_args:
                    command = command[:-1] + auth_args + [command[-1]]
                retries = 1 if youtube_mode == "compat" else 0
                proc = None

                for attempt in range(retries + 1):
                    try:
                        proc = subprocess.run(
                            command,
                            capture_output=True,
                            text=True,
                            timeout=self.settings.subtitle_fetch_timeout_seconds,
                            check=False,
                        )
                    except FileNotFoundError as exc:
                        raise SubtitleError(
                            "yt_dlp_not_installed",
                            "yt-dlp is not installed. Please run pip install -r backend/requirements.txt.",
                            str(exc),
                        ) from exc
                    except subprocess.TimeoutExpired as exc:
                        raise SubtitleError(
                            "subtitle_fetch_timeout",
                            "Subtitle fetching timed out. Please try again.",
                            str(exc),
                        ) from exc

                    if proc.returncode == 0:
                        break

                    combined_output = "\n".join(
                        part for part in [proc.stderr or "", proc.stdout or ""] if part
                    )
                    if is_subtitle_absence_error(combined_output):
                        return None

                    error = map_yt_dlp_error(combined_output)
                    last_error = error
                    logger.warning(
                        "yt_subtitle_attempt_failed code=%s extractor_args=%s auth_mode=%s detail=%s",
                        error.code,
                        extractor_args,
                        auth_args[0] if auth_args else "none",
                        _error_excerpt(error.raw_message),
                    )
                    if error.code == "cookies_db_locked":
                        break
                    if error.code == "bot_or_rate_limited":
                        if youtube_mode == "compat" and attempt < retries:
                            time.sleep(2.0)
                            continue
                        if youtube_mode == "compat":
                            next_extractor = True
                            break
                        raise error
                    raise error

                if proc is not None and proc.returncode == 0:
                    break
                if next_extractor:
                    break
            else:
                continue
            if next_extractor:
                continue
            if proc is not None and proc.returncode == 0:
                break
        else:
            if last_error is not None:
                raise last_error

        subtitle_files = sorted(output_dir.glob("*.vtt"))
        if not subtitle_files:
            return None

        # A single run can generate multiple files; pick best match for language preference.
        ranked = sorted(subtitle_files, key=lambda item: _score_file(item, language_pref), reverse=True)
        return ranked[0]

    def download_audio(
        self,
        url: str,
        output_dir: Path,
        cookies_file: Path | None = None,
        youtube_client: str | None = None,
        youtube_mode: str = "strict",
    ) -> Path:
        output_tpl = str(output_dir / "audio.%(ext)s")
        last_error: SubtitleError | None = None
        for extractor_args in _extractor_arg_candidates(
            self.settings,
            has_cookies=cookies_file is not None,
            youtube_client=youtube_client,
            youtube_mode=youtube_mode,
        ):
            base_command = [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-config-locations",
                "--no-playlist",
                "--format",
                "bestaudio[ext=m4a]/bestaudio/best",
                "--output",
                output_tpl,
            ]
            if self.settings.ytdlp_js_runtimes.strip():
                base_command.extend(["--js-runtimes", self.settings.ytdlp_js_runtimes.strip()])
            if self.settings.ytdlp_remote_components.strip():
                base_command.extend(["--remote-components", self.settings.ytdlp_remote_components.strip()])
            if extractor_args:
                base_command.extend(["--extractor-args", extractor_args])
            base_command.append(url)

            logger.info(
                "yt_audio_attempt extractor_args=%s has_user_cookies=%s mode=%s",
                extractor_args,
                cookies_file is not None,
                youtube_mode,
            )
            next_extractor = False
            for auth_args in _auth_candidates(self.settings, user_cookies_file=cookies_file):
                command = [*base_command]
                if auth_args:
                    command = command[:-1] + auth_args + [command[-1]]
                retries = 1 if youtube_mode == "compat" else 0
                proc = None

                for attempt in range(retries + 1):
                    try:
                        proc = subprocess.run(
                            command,
                            capture_output=True,
                            text=True,
                            timeout=self.settings.subtitle_fetch_timeout_seconds,
                            check=False,
                        )
                    except FileNotFoundError as exc:
                        raise SubtitleError(
                            "yt_dlp_not_installed",
                            "yt-dlp is not installed. Please run pip install -r backend/requirements.txt.",
                            str(exc),
                        ) from exc
                    except subprocess.TimeoutExpired as exc:
                        raise SubtitleError(
                            "youtube_audio_download_timeout",
                            "Downloading YouTube audio timed out. Please try again.",
                            str(exc),
                        ) from exc

                    if proc.returncode == 0:
                        break

                    combined_output = "\n".join(
                        part for part in [proc.stderr or "", proc.stdout or ""] if part
                    )
                    error = map_yt_dlp_error(combined_output)
                    last_error = error
                    logger.warning(
                        "yt_audio_attempt_failed code=%s extractor_args=%s auth_mode=%s detail=%s",
                        error.code,
                        extractor_args,
                        auth_args[0] if auth_args else "none",
                        _error_excerpt(error.raw_message),
                    )
                    if error.code == "cookies_db_locked":
                        break
                    if error.code == "bot_or_rate_limited":
                        if youtube_mode == "compat" and attempt < retries:
                            time.sleep(2.0)
                            continue
                        if youtube_mode == "compat":
                            next_extractor = True
                            break
                        raise error
                    raise error

                if proc is not None and proc.returncode == 0:
                    break
                if next_extractor:
                    break
            else:
                continue
            if next_extractor:
                continue
            if proc is not None and proc.returncode == 0:
                break
        else:
            if last_error is not None:
                raise last_error

        audio_files = sorted(
            [
                path
                for path in output_dir.glob("audio.*")
                if path.is_file() and not path.name.endswith(".part")
            ],
            key=lambda path: path.stat().st_size,
            reverse=True,
        )
        if not audio_files:
            raise SubtitleError(
                "youtube_audio_download_failed",
                "Failed to download YouTube audio for ASR fallback.",
                None,
            )
        return audio_files[0]
