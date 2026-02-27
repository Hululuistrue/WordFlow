from urllib.parse import parse_qs, urlparse


VALID_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def normalize_youtube_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must start with http:// or https://")
    if parsed.netloc.lower() not in VALID_HOSTS:
        raise ValueError("Only YouTube URLs are supported")

    host = parsed.netloc.lower()
    if "youtu.be" in host:
        video_id = parsed.path.strip("/").split("/")[0]
        if not video_id:
            raise ValueError("Invalid YouTube short URL")
        return f"https://www.youtube.com/watch?v={video_id}"

    query = parse_qs(parsed.query)
    video_id_list = query.get("v", [])
    video_id = video_id_list[0] if video_id_list else ""
    if not video_id:
        raise ValueError("YouTube URL is missing video id")
    return f"https://www.youtube.com/watch?v={video_id}"

