"""SRT and TXT generation from translated segments."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from utils.transcriber import Segment


def _format_ts(seconds: float) -> str:
    """Format a float seconds value as ``HH:MM:SS,mmm`` for SRT."""

    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(segments: Iterable[Segment], path: Path) -> Path:
    """Write a valid SRT file. Returns the path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        # Guarantee end > start so players don't reject the cue.
        end = seg.end if seg.end > seg.start else seg.start + 0.5
        lines.append(str(i))
        lines.append(f"{_format_ts(seg.start)} --> {_format_ts(end)}")
        lines.append(seg.text.strip() or "...")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_txt(segments: Iterable[Segment], path: Path) -> Path:
    """Write a transcript txt with one translated segment per line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join((seg.text.strip() or "...") for seg in segments)
    path.write_text(body + "\n", encoding="utf-8")
    return path
