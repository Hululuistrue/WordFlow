from pathlib import Path

from app.core.config import Settings
from app.services.youtube import _auth_candidates, _extractor_arg_candidates, _language_patterns


def test_auth_candidates_with_cookies_file_and_multiple_browsers() -> None:
    settings = Settings(
        ytdlp_cookies_file="D:\\cookies.txt",
        ytdlp_cookies_from_browser="chrome, edge",
    )
    candidates = _auth_candidates(settings)
    assert candidates == [
        ["--cookies", "D:\\cookies.txt"],
        ["--cookies-from-browser", "chrome"],
        ["--cookies-from-browser", "edge"],
        [],
    ]


def test_auth_candidates_without_cookie_settings() -> None:
    settings = Settings(
        ytdlp_cookies_file="",
        ytdlp_cookies_from_browser="",
    )
    candidates = _auth_candidates(settings)
    assert candidates == [[]]


def test_language_patterns_auto_uses_all_subtitles() -> None:
    assert _language_patterns("auto") == "all,-live_chat"


def test_auth_candidates_with_user_cookies_file_has_highest_priority() -> None:
    settings = Settings(
        ytdlp_cookies_file="D:\\cookies.txt",
        ytdlp_cookies_from_browser="chrome",
    )
    candidates = _auth_candidates(settings, user_cookies_file=Path("D:\\user-cookies.txt"))
    assert candidates == [["--cookies", "D:\\user-cookies.txt"]]


def test_extractor_arg_candidates_use_configured_default_only() -> None:
    settings = Settings(ytdlp_extractor_args="youtube:player_client=web")
    candidates = _extractor_arg_candidates(settings)
    assert candidates == ["youtube:player_client=web"]


def test_extractor_arg_candidates_allow_explicit_client_selection() -> None:
    settings = Settings(ytdlp_extractor_args="youtube:player_client=web")
    candidates = _extractor_arg_candidates(settings, youtube_client="android_web")
    assert candidates == ["youtube:player_client=android,web"]


def test_extractor_arg_candidates_compat_mode_limits_attempts_to_three() -> None:
    settings = Settings(ytdlp_extractor_args="youtube:player_client=web")
    candidates = _extractor_arg_candidates(settings, has_cookies=True, youtube_client="web", youtube_mode="compat")
    assert candidates == [
        "youtube:player_client=web",
        "youtube:player_client=web,ios",
        "youtube:player_client=ios,web",
    ]
