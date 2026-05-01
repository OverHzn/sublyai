"""Subtitle file writers (SRT / VTT / ASS) plus a JSON segments dump.

Segments are also persisted as a side-by-side JSON file so the inline
subtitle editor in the UI can load them, let the user tweak the text, and
regenerate the subtitle files without re-running Whisper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from utils.transcriber import Segment


# -- Timestamp formatters ----------------------------------------------------

def _format_ts_srt(seconds: float) -> str:
    """``HH:MM:SS,mmm`` (SRT)."""

    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_ts_vtt(seconds: float) -> str:
    """``HH:MM:SS.mmm`` (WebVTT)."""

    return _format_ts_srt(seconds).replace(",", ".")


def _format_ts_ass(seconds: float) -> str:
    """``H:MM:SS.cc`` (ASS uses centiseconds, single-digit hours)."""

    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _safe_end(seg: Segment) -> float:
    """Guarantee ``end > start`` so picky players don't reject a cue."""

    return seg.end if seg.end > seg.start else seg.start + 0.5


# -- Writers -----------------------------------------------------------------

def write_srt(segments: Iterable[Segment], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_format_ts_srt(seg.start)} --> {_format_ts_srt(_safe_end(seg))}")
        lines.append(seg.text.strip() or "...")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_txt(segments: Iterable[Segment], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join((seg.text.strip() or "...") for seg in segments)
    path.write_text(body + "\n", encoding="utf-8")
    return path


def write_vtt(segments: Iterable[Segment], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["WEBVTT", ""]
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_format_ts_vtt(seg.start)} --> {_format_ts_vtt(_safe_end(seg))}")
        lines.append(seg.text.strip() or "...")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_ass(segments: Iterable[Segment], path: Path) -> Path:
    """Write an Advanced SubStation Alpha (.ass) file with a default style."""

    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Inter,42,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,30,30,40,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    body_lines: list[str] = []
    for seg in segments:
        text = (seg.text or "").replace("\n", "\\N").strip()
        if not text:
            text = "..."
        body_lines.append(
            "Dialogue: 0,"
            f"{_format_ts_ass(seg.start)},"
            f"{_format_ts_ass(_safe_end(seg))},"
            f"Default,,0,0,0,,{text}"
        )
    path.write_text(header + "\n".join(body_lines) + "\n", encoding="utf-8")
    return path


# -- Editable segments JSON --------------------------------------------------

def write_segments_json(segments: Iterable[Segment], path: Path) -> Path:
    """Dump segments as JSON so the inline editor can round-trip them."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [seg.to_dict() for seg in segments]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_segments_json(path: Path) -> list[Segment]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    out: list[Segment] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(Segment.from_dict(item))
    return out
