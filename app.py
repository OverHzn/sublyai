"""SublyAI – FastAPI application.

Routes
------
GET  /
GET  /api/jobs/{job_id}
POST /api/jobs
GET  /download/{job_id}/{kind}    kind in {srt, txt, original, video}

The heavy work (download, ffmpeg, Whisper, translate, srt/txt, optional
burn-in) runs on a background thread launched via FastAPI's BackgroundTasks
so the HTTP request returns immediately with a job_id. State is persisted to
``jobs/<job_id>.json`` and polled by the browser.
"""

from __future__ import annotations

import logging
import re
import threading
import traceback
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
from utils import jobs as jobs_mod
from utils.downloader import DownloadError, download
from utils.jobs import Job, JobFiles
from utils.media import FFmpegError, FFmpegMissing, burn_subtitle, extract_audio
from utils.subtitle import write_srt, write_txt
from utils.transcriber import transcribe
from utils.translator import translate_segments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("sublyai")

app = FastAPI(title=config.APP_NAME, description=config.APP_DESCRIPTION)
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))


_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    if not url or not _URL_RE.match(url):
        raise HTTPException(status_code=400, detail="Please provide a valid http(s) URL.")
    return url


def _validate_quality(quality: str) -> str:
    if quality not in config.ALLOWED_QUALITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported quality {quality!r}. Allowed: {list(config.ALLOWED_QUALITIES)}",
        )
    return quality


def _set(job_id: str, *, status=None, progress=None, message=None, error=None, files=None) -> None:
    jobs_mod.update_job(
        job_id,
        status=status,
        progress=progress,
        message=message,
        error=error,
        files=files,
    )


def _public_files(job_id: str, *, srt: Path, txt: Path, video: Path | None) -> JobFiles:
    """Build the public ``files`` mapping returned to the browser."""

    files = JobFiles()
    if srt.exists():
        files.srt = f"/download/{job_id}/srt"
    if txt.exists():
        files.txt = f"/download/{job_id}/txt"
    if jobs_mod.find_original_media(job_id):
        files.original = f"/download/{job_id}/original"
    if video is not None and video.exists():
        files.video = f"/download/{job_id}/video"
    return files


def _process_job(job_id: str) -> None:
    """The entire pipeline for a single job. Never raises."""

    log.info("Job %s: worker thread started", job_id)
    try:
        job = jobs_mod.load_job(job_id)
        if job is None:
            log.error("Job %s vanished before processing", job_id)
            return

        out_dir = jobs_mod.job_output_dir(job_id)
        srt_path = out_dir / "subtitle_id.srt"
        txt_path = out_dir / "transcript_id.txt"
        burn_path = out_dir / "video_subtitle.mp4"

        # 1. Download
        _set(job_id, status="processing", progress=2, message="Starting media download…")
        media_path = download(
            job.url,
            job_id,
            job.quality,
            job.burn_video,
            progress_callback=lambda pct, msg: _set(
                job_id,
                progress=2 + int(pct * 0.18),  # download stage = 2..20%
                message=msg,
            ),
        )
        _set(job_id, progress=22, message="Media downloaded successfully…")

        # 2. Audio extraction
        _set(job_id, progress=25, message="Extracting audio…")
        audio_path = extract_audio(media_path, out_dir)

        # 3. Transcribe
        _set(job_id, progress=32, message="AI is creating timestamps…")
        segments = transcribe(audio_path)
        if not segments:
            raise RuntimeError("Transcription returned no segments. Is the audio silent?")
        _set(job_id, progress=65, message=f"Transcribed {len(segments)} segments.")

        # 4. Translate
        _set(job_id, progress=70, message="Translating subtitles to Indonesian…")
        translated = translate_segments(segments)

        # 5. Write SRT + TXT
        _set(job_id, progress=85, message="Generating SRT and TXT files…")
        write_srt(translated, srt_path)
        write_txt(translated, txt_path)

        burn_out: Path | None = None
        if job.burn_video:
            _set(job_id, progress=90, message="Burning subtitle into video…")
            try:
                burn_out = burn_subtitle(media_path, srt_path, burn_path)
            except (FFmpegError, FFmpegMissing) as e:
                # Don't fail the whole job; surface as a warning in the message
                log.warning("Burn-in failed for %s: %s", job_id, e)
                _set(
                    job_id,
                    message=(
                        "Subtitles ready. Burn-in skipped: " + str(e).split("\n")[0][:200]
                    ),
                )

        files = _public_files(job_id, srt=srt_path, txt=txt_path, video=burn_out)
        _set(
            job_id,
            status="done",
            progress=100,
            message="Done. Your files are ready to download.",
            files=files,
        )

    except DownloadError as e:
        log.error("Download failed for %s: %s", job_id, e)
        _set(
            job_id,
            status="failed",
            error=f"Download failed: {e}",
            message="Download failed.",
        )
    except FFmpegMissing as e:
        log.error("ffmpeg missing for %s: %s", job_id, e)
        _set(
            job_id,
            status="failed",
            error=str(e),
            message="ffmpeg is not installed on the server.",
        )
    except FFmpegError as e:
        log.error("ffmpeg failed for %s: %s", job_id, e)
        _set(
            job_id,
            status="failed",
            error=f"ffmpeg error: {e}",
            message="Audio/video processing failed.",
        )
    except Exception as e:  # noqa: BLE001 - never crash the worker
        log.error("Unhandled job error %s: %s\n%s", job_id, e, traceback.format_exc())
        _set(
            job_id,
            status="failed",
            error=f"Unexpected error: {e}",
            message="Something went wrong.",
        )


# -- Routes -----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": config.APP_NAME,
            "tagline": config.APP_TAGLINE,
            "description": config.APP_DESCRIPTION,
            "qualities": config.ALLOWED_QUALITIES,
            "default_quality": config.DEFAULT_QUALITY,
        },
    )


def _start_worker(job_id: str) -> None:
    """Spawn a daemon thread that runs the pipeline for ``job_id``.

    We use a real thread rather than FastAPI's BackgroundTasks because the
    pipeline is sync, CPU-heavy, and minutes long — it would otherwise tie up
    the event loop.
    """

    t = threading.Thread(target=_process_job, args=(job_id,), daemon=True)
    t.start()


@app.post("/api/jobs")
async def create_job_endpoint(
    url: str = Form(...),
    quality: str = Form(config.DEFAULT_QUALITY),
    burn_video: str | None = Form(None),
) -> dict:
    url = _validate_url(url)
    quality = _validate_quality(quality)
    burn = str(burn_video).lower() in ("1", "true", "on", "yes") if burn_video else False
    job = jobs_mod.create_job(url=url, quality=quality, burn_video=burn)
    _start_worker(job.job_id)
    return {"job_id": job.job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = jobs_mod.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


KindT = Literal["srt", "txt", "original", "video"]


@app.get("/download/{job_id}/{kind}")
async def download_artifact(job_id: str, kind: KindT) -> FileResponse:
    job = jobs_mod.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    out_dir = config.OUTPUTS_DIR / job_id

    if kind == "srt":
        path = out_dir / "subtitle_id.srt"
        if not path.exists():
            raise HTTPException(status_code=404, detail="SRT not generated yet.")
        return FileResponse(path, filename=f"{job_id}_subtitle_id.srt", media_type="application/x-subrip")

    if kind == "txt":
        path = out_dir / "transcript_id.txt"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Transcript not generated yet.")
        return FileResponse(path, filename=f"{job_id}_transcript_id.txt", media_type="text/plain")

    if kind == "video":
        path = out_dir / "video_subtitle.mp4"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Burned video not generated.")
        return FileResponse(path, filename=f"{job_id}_video_subtitle.mp4", media_type="video/mp4")

    if kind == "original":
        path = jobs_mod.find_original_media(job_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Original media not found.")
        return FileResponse(path, filename=path.name)

    raise HTTPException(status_code=400, detail=f"Unknown kind {kind!r}.")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
