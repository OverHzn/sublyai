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

# Whisper model sizes the user can pick from in the UI. The string value is
# what we pass to faster-whisper's WhisperModel constructor.
WHISPER_MODELS: tuple[tuple[str, str], ...] = (
    ("tiny",     "Tiny — fastest, lowest accuracy (~75 MB)"),
    ("base",     "Base — quick, decent accuracy (~150 MB)"),
    ("small",    "Small — balanced (default, ~500 MB)"),
    ("medium",   "Medium — higher accuracy (~1.5 GB, slower)"),
    ("large-v3", "Large v3 — best accuracy (~3 GB, much slower)"),
)
ALLOWED_WHISPER_MODELS = tuple(m for m, _ in WHISPER_MODELS)

# Translation target — any language code Google Translate via deep-translator
# accepts. Keep this list curated; users can still pass an arbitrary code.
TRANSLATE_TARGET_LANG = os.getenv("SUBLYAI_TRANSLATE_TARGET", "id")

TARGET_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("id",    "Indonesian (default)"),
    ("en",    "English"),
    ("ja",    "Japanese"),
    ("ko",    "Korean"),
    ("zh-CN", "Chinese (Simplified)"),
    ("zh-TW", "Chinese (Traditional)"),
    ("ar",    "Arabic"),
    ("es",    "Spanish"),
    ("pt",    "Portuguese"),
    ("fr",    "French"),
    ("de",    "German"),
    ("ru",    "Russian"),
    ("hi",    "Hindi"),
    ("vi",    "Vietnamese"),
    ("th",    "Thai"),
    ("tl",    "Filipino (Tagalog)"),
    ("ms",    "Malay"),
    ("tr",    "Turkish"),
    ("nl",    "Dutch"),
    ("it",    "Italian"),
)

# Subtitle burn-in styling. ffmpeg's `subtitles=` filter accepts ASS
# `force_style` — keys mirror libass field names.
STYLE_FONTS: tuple[str, ...] = (
    "Inter", "Arial", "Roboto", "Helvetica", "Verdana",
    "Tahoma", "Trebuchet MS", "Georgia", "Times New Roman",
    "Courier New", "Comic Sans MS",
)
STYLE_POSITIONS: tuple[tuple[str, str], ...] = (
    # ASS Alignment value -> human label. 1=BL, 2=BC, 3=BR, 4=ML, 5=MC,
    # 6=MR, 7=TL, 8=TC, 9=TR.
    ("2", "Bottom (default)"),
    ("8", "Top"),
    ("5", "Center"),
    ("1", "Bottom-left"),
    ("3", "Bottom-right"),
    ("7", "Top-left"),
    ("9", "Top-right"),
)
STYLE_DEFAULTS = {
    "font_name": "Inter",
    "font_size": 22,
    "font_color": "#FFFFFF",  # primary fill
    "outline_color": "#000000",
    "alignment": "2",
    "outline": 2,
}

# Media extensions we treat as "original media" for the download endpoint.
ORIGINAL_MEDIA_EXTS = (".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".wav", ".aac", ".opus")

# Limit on uploaded files (in bytes). 1 GiB is plenty for typical workflows
# but caps memory use if someone tries to drop a 50 GB file in.
MAX_UPLOAD_BYTES = int(os.getenv("SUBLYAI_MAX_UPLOAD_BYTES", str(1024 * 1024 * 1024)))
