"""yt-dlp wrapper for SublyAI.

Picks a format string from ``config.QUALITY_FORMATS`` and downloads to
``downloads/<job_id>/``. ``burn_video=True`` forces a video format even when
the user asked for ``audio`` (we cannot burn subtitles into audio).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import yt_dlp

import config

log = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    """Raised when yt-dlp cannot fetch the requested URL."""


def _resolve_format(quality: str, burn_video: bool) -> str:
    """Pick a yt-dlp format string for the requested quality.

    If the user enabled burn-subtitle but selected audio-only, we transparently
    upgrade to 480p so the burn step actually has a video stream to work with.
    """

    if quality not in config.QUALITY_FORMATS:
        raise ValueError(f"Unsupported quality: {quality!r}")
    if burn_video and quality == "audio":
        quality = "480"
    return config.QUALITY_FORMATS[quality]


def download(
    url: str,
    job_id: str,
    quality: str,
    burn_video: bool,
    progress_callback: Callable[[int, str], None] | None = None,
) -> Path:
    """Download ``url`` into ``downloads/<job_id>/`` and return the media path.

    ``progress_callback`` is invoked with ``(percent, message)`` where percent
    is 0..100 mapped within the download stage of the overall job.
    """

    out_dir = config.DOWNLOADS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = _resolve_format(quality, burn_video)

    def _hook(d: dict) -> None:
        if progress_callback is None:
            return
        try:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = int(done * 100 / total) if total else 0
                progress_callback(pct, "Starting media download…")
            elif d.get("status") == "finished":
                progress_callback(100, "Media downloaded successfully…")
        except Exception:
            # Progress bookkeeping must never abort the actual media download.
            log.debug("progress callback failed", exc_info=True)

    ydl_opts: dict = {
        "format": fmt,
        "outtmpl": str(out_dir / "%(title).80B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "continuedl": True,
        "socket_timeout": 30,
        "merge_output_format": "mp4",
        "progress_hooks": [_hook],
        "concurrent_fragment_downloads": 4,
        "overwrites": False,
    }

    if quality == "audio" and not burn_video:
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "0",
            }
        ]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise DownloadError("yt-dlp returned no info for this URL.")
            filename = ydl.prepare_filename(info)
    except yt_dlp.utils.DownloadError as e:
        raise DownloadError(str(e)) from e
    except Exception as e:  # noqa: BLE001 - propagate as DownloadError
        raise DownloadError(f"Unexpected yt-dlp error: {e}") from e

    media_path = Path(filename)
    if not media_path.exists():
        # post-processing may have changed the extension; pick newest media file
        candidates: list[Path] = []
        for ext in config.ORIGINAL_MEDIA_EXTS:
            candidates.extend(out_dir.glob(f"*{ext}"))
        if not candidates:
            raise DownloadError("Download finished but no media file was produced.")
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        media_path = candidates[0]

    return media_path
