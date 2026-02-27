import pytest

from app.utils.url_validator import normalize_youtube_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc123", "https://www.youtube.com/watch?v=abc123"),
        ("https://youtube.com/watch?v=xyz789&t=10", "https://www.youtube.com/watch?v=xyz789"),
        ("https://youtu.be/helloID", "https://www.youtube.com/watch?v=helloID"),
    ],
)
def test_normalize_youtube_url_valid(raw: str, expected: str) -> None:
    assert normalize_youtube_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://vimeo.com/123",
        "youtube.com/watch?v=abc",
        "https://www.youtube.com/watch",
        "https://youtu.be/",
    ],
)
def test_normalize_youtube_url_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_youtube_url(raw)

