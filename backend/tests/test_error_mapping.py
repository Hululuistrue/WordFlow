from app.services.errors import map_yt_dlp_error


def test_map_private_video_error() -> None:
    exc = map_yt_dlp_error("ERROR: Private video. Sign in if you've been granted access.")
    assert exc.code == "private_video"
    assert "private" in exc.user_message.lower()


def test_map_region_error() -> None:
    exc = map_yt_dlp_error("ERROR: This video is not available in your country.")
    assert exc.code == "region_restricted"


def test_map_default_error() -> None:
    exc = map_yt_dlp_error("ERROR: unexpected extractor error")
    assert exc.code == "subtitle_fetch_failed"


def test_map_no_subtitles_error() -> None:
    exc = map_yt_dlp_error("ERROR: Unable to download video subtitles for 'en': HTTP Error 404: Not Found")
    assert exc.code == "subtitle_unavailable"


def test_map_bot_or_rate_limited_error() -> None:
    exc = map_yt_dlp_error("ERROR: Sign in to confirm you're not a bot. HTTP Error 429: Too Many Requests")
    assert exc.code == "bot_or_rate_limited"


def test_map_bot_or_rate_limited_error_without_apostrophe() -> None:
    exc = map_yt_dlp_error("ERROR: Sign in to confirm youre not a bot.")
    assert exc.code == "bot_or_rate_limited"


def test_map_js_runtime_missing_error() -> None:
    exc = map_yt_dlp_error("WARNING: No supported JavaScript runtime could be found.")
    assert exc.code == "js_runtime_missing"


def test_map_bot_or_rate_limited_error_with_cookies_hint() -> None:
    exc = map_yt_dlp_error("ERROR: Sign in to confirm. Use --cookies-from-browser or --cookies")
    assert exc.code == "bot_or_rate_limited"


def test_map_cookie_database_locked_error() -> None:
    exc = map_yt_dlp_error("ERROR: Could not copy Chrome cookie database.")
    assert exc.code == "cookies_db_locked"
