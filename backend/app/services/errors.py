class SubtitleError(Exception):
    def __init__(self, code: str, user_message: str, raw_message: str | None = None):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.raw_message = raw_message


def _normalize(text: str | None) -> str:
    return (text or "").lower()


def is_subtitle_absence_error(stderr: str | None) -> bool:
    text = _normalize(stderr)
    subtitle_absent_patterns = [
        "unable to download video subtitles",
        "there are no subtitles for the requested languages",
        "video has no subtitles",
        "no subtitles",
        "did not get any subtitles",
    ]
    return any(pattern in text for pattern in subtitle_absent_patterns)


def map_yt_dlp_error(stderr: str) -> SubtitleError:
    text = _normalize(stderr)
    if "could not copy" in text and "cookie database" in text:
        return SubtitleError(
            "cookies_db_locked",
            "Failed to read browser cookies. Close Chrome completely, or use YTDLP_COOKIES_FILE with an exported cookies.txt.",
            stderr,
        )
    if "private video" in text:
        return SubtitleError("private_video", "This video is private and cannot be processed.", stderr)
    if "video unavailable" in text or "this video is unavailable" in text:
        return SubtitleError("video_unavailable", "This video is unavailable.", stderr)
    if "not available in your country" in text or "geo restricted" in text:
        return SubtitleError("region_restricted", "This video is region restricted.", stderr)
    if "sign in to confirm your age" in text or "age-restricted" in text:
        return SubtitleError("age_restricted", "This video is age restricted.", stderr)
    if (
        "sign in to confirm you're not a bot" in text
        or "sign in to confirm youre not a bot" in text
        or "confirm you are not a bot" in text
        or "not a bot" in text
        or ("sign in to confirm" in text and "cookies-from-browser" in text)
        or "use --cookies-from-browser or --cookies" in text
        or "http error 429" in text
        or "too many requests" in text
    ):
        return SubtitleError(
            "bot_or_rate_limited",
            "YouTube is blocking requests (bot check/rate limit). Configure valid cookies (uploaded cookies.txt or cookies-from-browser) and retry.",
            stderr,
        )
    if "no supported javascript runtime could be found" in text:
        return SubtitleError(
            "js_runtime_missing",
            "No JavaScript runtime available for yt-dlp. Install Node.js and retry.",
            stderr,
        )
    if "members-only content" in text:
        return SubtitleError(
            "members_only",
            "This video is members-only and cannot be processed.",
            stderr,
        )
    if is_subtitle_absence_error(stderr):
        return SubtitleError(
            "subtitle_unavailable",
            "No subtitles were found for this video.",
            stderr,
        )
    if "no module named yt_dlp" in text:
        return SubtitleError(
            "yt_dlp_not_installed",
            "yt-dlp is not installed. Please run pip install -r backend/requirements.txt.",
            stderr,
        )
    return SubtitleError("subtitle_fetch_failed", "Failed to fetch subtitles.", stderr)
