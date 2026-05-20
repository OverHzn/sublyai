# SublyAI — production-ish image for FastAPI + yt-dlp + ffmpeg + faster-whisper.
#
# Layout:
#   /app           — application code (read-only at runtime)
#   /app/downloads — yt-dlp output (mount a host volume here)
#   /app/outputs   — generated SRT/TXT/burned MP4 (mount a host volume here)
#   /app/jobs      — per-job JSON state files (mount a host volume here)
#   /app/config    — app-level config (LLM credentials, etc.); mount a host volume
#   /home/app/.cache/huggingface — whisper model cache (mount a named volume)
#
# The container starts as root so the entrypoint can fix ownership of
# bind-mounted host directories (which inherit their host owner on first
# mount) and then drops privileges to the unprivileged ``app`` user via
# gosu before exec'ing uvicorn.

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
        gosu \
 && rm -rf /var/lib/apt/lists/*

# Non-root runtime user. uid/gid 1000 matches a typical desktop user so any
# files written into bind-mounted volumes look sane on the host.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid app --create-home --shell /bin/bash app

WORKDIR /app

# Install Python deps first so they're cached across code edits.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the app and ensure the runtime dirs exist.
COPY . /app
RUN mkdir -p /app/downloads /app/outputs /app/jobs /app/config \
              /home/app/.cache/huggingface/hub \
 && chown -R app:app /app /home/app \
 && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# The unauth'd index page returns 200 once the app is ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/ >/dev/null || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
