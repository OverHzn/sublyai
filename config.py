"""SublyAI configuration.

All paths and tunables in one place. Override via environment variables when
deploying. Nothing here hardcodes a public URL or local-only path so the same
config works on Windows, Ubuntu VPS, and behind ngrok.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DOWNLOADS_DIR = Path(os.getenv("SUBLYAI_DOWNLOADS_DIR", BASE_DIR / "downloads"))
OUTPUTS_DIR = Path(os.getenv("SUBLYAI_OUTPUTS_DIR", BASE_DIR / "outputs"))
JOBS_DIR = Path(os.getenv("SUBLYAI_JOBS_DIR", BASE_DIR / "jobs"))

for _d in (DOWNLOADS_DIR, OUTPUTS_DIR, JOBS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Branding
APP_NAME = "SublyAI"
APP_TAGLINE = "Paste link. Generate Indonesian subtitles instantly."
APP_DESCRIPTION = (
    "Turn video links into accurate Indonesian subtitles, transcripts, "
    "and downloadable media."
)

# yt-dlp quality format strings.
QUALITY_FORMATS: dict[str, str] = {
    "audio": "bestaudio/best",
    "480": (
        "bv*[height<=480][ext=mp4]+ba[ext=m4a]/"
        "b[height<=480][ext=mp4]/best[height<=480]/best"
    ),
    "720": (
        "bv*[height<=720][ext=mp4]+ba[ext=m4a]/"
        "b[height<=720][ext=mp4]/best[height<=720]/best"
    ),
    "1080": (
        "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
        "b[height<=1080][ext=mp4]/best[height<=1080]/best"
    ),
    "best": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
}

ALLOWED_QUALITIES = tuple(QUALITY_FORMATS.keys())
DEFAULT_QUALITY = "480"

# Whisper / transcription
WHISPER_MODEL = os.getenv("SUBLYAI_WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("SUBLYAI_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("SUBLYAI_WHISPER_COMPUTE_TYPE", "int8")

# Translation target
TRANSLATE_TARGET_LANG = os.getenv("SUBLYAI_TRANSLATE_TARGET", "id")

# Media extensions we treat as "original media" for the download endpoint.
ORIGINAL_MEDIA_EXTS = (".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".wav", ".aac", ".opus")
