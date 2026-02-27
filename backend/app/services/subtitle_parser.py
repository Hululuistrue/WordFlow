import re

from app.models.task import TranscriptSegment


TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{2}:)?\d{2}:\d{2}\.\d{3}\s+-->\s+(?P<end>\d{2}:)?\d{2}:\d{2}\.\d{3}"
)
TAG_RE = re.compile(r"<[^>]+>")


def parse_vtt_timestamp(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, sec_ms = parts
    else:
        hours, minutes, sec_ms = parts
    seconds, millis = sec_ms.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_vtt(vtt_text: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    lines = vtt_text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if "-->" not in line or not TIMESTAMP_RE.search(line):
            index += 1
            continue

        left, right = [part.strip() for part in line.split("-->", 1)]
        start = parse_vtt_timestamp(left.split(" ")[0])
        end = parse_vtt_timestamp(right.split(" ")[0])

        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            raw = lines[index].strip()
            cleaned = TAG_RE.sub("", raw).replace("&nbsp;", " ").strip()
            if cleaned:
                text_lines.append(cleaned)
            index += 1

        # Duplicate lines can appear in some auto-generated subtitles.
        unique_lines = list(dict.fromkeys(text_lines))
        text = " ".join(unique_lines).strip()
        if text:
            segments.append(TranscriptSegment(start=start, end=end, text=text))
        index += 1

    return segments


def segments_to_text(segments: list[TranscriptSegment], with_timestamps: bool) -> str:
    if with_timestamps:
        return "\n".join(f"[{seg.start:0.3f}-{seg.end:0.3f}] {seg.text}" for seg in segments)
    return "\n".join(seg.text for seg in segments)

