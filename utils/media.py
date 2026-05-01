"""ffmpeg helpers: audio extraction + subtitle burn-in."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import config

log = logging.getLogger(__name__)


class FFmpegMissing(RuntimeError):
    """ffmpeg binary not on PATH."""


class FFmpegError(RuntimeError):
    """ffmpeg ran but exited non-zero."""


def _ffmpeg_bin() -> str:
    bin_path = shutil.which("ffmpeg")
    if not bin_path:
        raise FFmpegMissing(
            "ffmpeg is not installed or not on PATH. "
            "Install ffmpeg and try again."
        )
    return bin_path


def extract_audio(media_path: Path, out_dir: Path) -> Path:
    """Extract media to 16kHz mono wav at ``out_dir/audio.wav``."""

    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / "audio.wav"
    ffmpeg = _ffmpeg_bin()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(
            f"ffmpeg audio extraction failed: {proc.stderr.strip()[-500:]}"
        )
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise FFmpegError("ffmpeg produced no audio output.")
    return audio_path


def _escape_subtitle_path(srt_path: Path) -> str:
    """Escape an SRT path for use inside ffmpeg's ``subtitles=`` filter."""

    s = str(srt_path).replace("\\", "/")
    if len(s) >= 2 and s[1] == ":":
        s = s[0] + r"\:" + s[2:]
    s = s.replace("'", r"\'")
    s = s.replace(",", r"\,")
    return s


@dataclass
class BurnStyle:
    """Per-job burn-in styling. ``None`` falls back to libass defaults."""

    font_name: str = "Inter"
    font_size: int = 22
    font_color: str = "#FFFFFF"     # CSS hex
    outline_color: str = "#000000"  # CSS hex
    alignment: str = "2"            # ASS Alignment 1..9 as a string
    outline: int = 2

    @classmethod
    def from_dict(cls, d: dict | None) -> "BurnStyle":
        d = d or {}
        defaults = config.STYLE_DEFAULTS
        try:
            font_size = int(d.get("font_size", defaults["font_size"]))
        except (TypeError, ValueError):
            font_size = int(defaults["font_size"])
        font_size = max(8, min(96, font_size))
        try:
            outline = int(d.get("outline", defaults["outline"]))
        except (TypeError, ValueError):
            outline = int(defaults["outline"])
        outline = max(0, min(8, outline))
        return cls(
            font_name=str(d.get("font_name") or defaults["font_name"]),
            font_size=font_size,
            font_color=str(d.get("font_color") or defaults["font_color"]),
            outline_color=str(d.get("outline_color") or defaults["outline_color"]),
            alignment=str(d.get("alignment") or defaults["alignment"]),
            outline=outline,
        )


def _hex_to_ass_bgr(color: str) -> str:
    """CSS hex (#RRGGBB) -> ASS ``&H00BBGGRR`` (alpha 00 = opaque)."""

    s = (color or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        s = "FFFFFF"
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
    except ValueError:
        r, g, b = 255, 255, 255
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _build_force_style(style: BurnStyle) -> str:
    """Return a libass ``force_style`` argument string."""

    primary = _hex_to_ass_bgr(style.font_color)
    outline = _hex_to_ass_bgr(style.outline_color)
    parts = [
        f"FontName={style.font_name}",
        f"Fontsize={style.font_size}",
        f"PrimaryColour={primary}",
        f"OutlineColour={outline}",
        "BorderStyle=1",
        f"Outline={style.outline}",
        "Shadow=0",
        f"Alignment={style.alignment}",
    ]
    return ",".join(parts)


def burn_subtitle(
    media_path: Path,
    srt_path: Path,
    out_path: Path,
    style: BurnStyle | None = None,
) -> Path:
    """Render ``srt_path`` into ``media_path`` and write to ``out_path``."""

    ffmpeg = _ffmpeg_bin()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sub_arg = _escape_subtitle_path(srt_path)
    if style is None:
        vf = f"subtitles='{sub_arg}'"
    else:
        force_style = _build_force_style(style)
        # The force_style value can contain ',' which is the libavfilter
        # parameter separator — escape it.
        force_style_escaped = force_style.replace(",", r"\,")
        vf = f"subtitles='{sub_arg}':force_style='{force_style_escaped}'"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(media_path),
        "-vf",
        vf,
        "-c:a",
        "copy",
        "-preset",
        "veryfast",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(
            f"ffmpeg subtitle burn failed: {proc.stderr.strip()[-500:]}"
        )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise FFmpegError("ffmpeg burn-in produced no output.")
    return out_path
