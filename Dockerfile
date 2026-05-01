# SublyAI — production-ish image for FastAPI + yt-dlp + ffmpeg + faster-whisper.
#
# Layout:
#   /app           — application code (read-only at runtime)
#   /app/downloads — yt-dlp output (mount a host volume here)
#   /app/outputs   — generated SRT/TXT/burned MP4 (mount a host volume here)
#   /app/jobs      — per-job JSON state files (mount a host volume here)
#   /home/app/.cache/huggingface — whisper model cache (mount a named volume)

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SUBLYAI_WHISPER_MODEL=small \
    SUBLYAI_WHISPER_DEVICE=cpu \
    SUBLYAI_WHISPER_COMPUTE_TYPE=int8

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root user — uid/gid 1000 matches a typical desktop user so bind-mounted
# host volumes (./downloads, ./outputs, ./jobs) inherit sane ownership.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid app --create-home --shell /bin/bash app

WORKDIR /app

# Install Python deps first so they're cached across code edits.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the app and ensure the runtime dirs exist.
# We pre-create /home/app/.cache/huggingface/hub *with the app user owning it*
# so a freshly-created Docker named volume mounted on top inherits the
# correct ownership (Docker copies the image's directory contents on the
# very first mount of an empty named volume).
COPY . /app
RUN mkdir -p /app/downloads /app/outputs /app/jobs \
              /home/app/.cache/huggingface/hub \
 && chown -R app:app /app /home/app

USER app

EXPOSE 8000

# Use the unauth'd FastAPI route — returns the index page (HTTP 200) once ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/ >/dev/null || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
