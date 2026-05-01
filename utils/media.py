"""ffmpeg helpers: audio extraction + subtitle burn-in."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

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
    """Escape an SRT path for use inside ffmpeg's ``subtitles=`` filter.

    The subtitles filter parses its argument as a libavfilter string, so
    backslashes, colons, single quotes and commas need escaping. Forward
    slashes work on both Windows and POSIX inside the filter string, so we
    normalize to forward slashes first.
    """

    s = str(srt_path).replace("\\", "/")
    # Drive-colon on Windows (e.g. C:/...) needs to be escaped to C\:/...
    if len(s) >= 2 and s[1] == ":":
        s = s[0] + r"\:" + s[2:]
    s = s.replace("'", r"\'")
    s = s.replace(",", r"\,")
    return s


def burn_subtitle(media_path: Path, srt_path: Path, out_path: Path) -> Path:
    """Render ``srt_path`` into ``media_path`` and write to ``out_path``."""

    ffmpeg = _ffmpeg_bin()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sub_arg = _escape_subtitle_path(srt_path)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(media_path),
        "-vf",
        f"subtitles='{sub_arg}'",
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
