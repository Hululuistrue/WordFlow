from app.api.v2.router import _normalize_cookies_text


def test_normalize_cookies_accepts_netscape_text() -> None:
    raw = ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tvalue123\n"
    normalized = _normalize_cookies_text(raw)
    assert normalized is not None
    assert "SID\tvalue123" in normalized


def test_normalize_cookies_converts_json_array() -> None:
    raw = """
[
  {
    "domain": ".youtube.com",
    "path": "/",
    "secure": true,
    "expirationDate": 2147483647,
    "name": "SID",
    "value": "abc"
  }
]
"""
    normalized = _normalize_cookies_text(raw)
    assert normalized is not None
    assert normalized.startswith("# Netscape HTTP Cookie File")
    assert ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tabc" in normalized


def test_normalize_cookies_converts_json_with_cookies_field() -> None:
    raw = """
{
  "cookies": [
    {
      "domain": "youtube.com",
      "hostOnly": true,
      "path": "/",
      "secure": false,
      "expires": 2147483647000,
      "name": "HSID",
      "value": "xyz"
    }
  ]
}
"""
    normalized = _normalize_cookies_text(raw)
    assert normalized is not None
    # Millisecond epoch should be normalized to seconds.
    assert "youtube.com\tFALSE\t/\tFALSE\t2147483647\tHSID\txyz" in normalized


def test_normalize_cookies_rejects_unknown_format() -> None:
    assert _normalize_cookies_text("hello_without_equals") is None


def test_normalize_cookies_accepts_cookie_header_text() -> None:
    raw = "Cookie: SID=abc123; HSID=xyz456; PREF=f6=400"
    normalized = _normalize_cookies_text(raw)
    assert normalized is not None
    assert ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tabc123" in normalized
    assert ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tHSID\txyz456" in normalized


def test_normalize_cookies_converts_json_using_url_field() -> None:
    raw = """
[
  {
    "url": "https://www.youtube.com/",
    "name": "SID",
    "value": "abc123",
    "path": "/",
    "secure": true
  }
]
"""
    normalized = _normalize_cookies_text(raw)
    assert normalized is not None
    assert "youtube.com\tFALSE\t/\tTRUE\t0\tSID\tabc123" in normalized
