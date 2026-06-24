"""SublyAI – FastAPI application.

Routes
------
GET  /                                     index page
GET  /healthz                              health probe
POST /api/jobs                             create job (URL or file upload)
GET  /api/jobs/{job_id}                    job status JSON
GET  /api/jobs/{job_id}/segments           translated segments JSON
PUT  /api/jobs/{job_id}/segments           replace segments + regenerate files
GET  /download/{job_id}/{kind}             kind in {srt, txt, vtt, ass, original, video}

The heavy work (download, ffmpeg, Whisper, translate, srt/txt/vtt/ass,
optional burn-in) runs on a background thread launched on job creation so the
HTTP request returns immediately with a job_id. State is persisted to
``jobs/<job_id>.json`` and polled by the browser every 2.5 seconds.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
from utils import jobs as jobs_mod
from utils import llm as llm_mod
from utils.downloader import DownloadError, download
from utils.jobs import Job, JobFiles
from utils.media import BurnStyle, FFmpegError, FFmpegMissing, burn_subtitle, extract_audio
from utils.subtitle import (
    read_segments_json,
    write_ass,
    write_segments_json,
    write_srt,
    write_txt,
    write_vtt,
)
from utils.transcriber import Segment, transcribe
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


def _validate_whisper_model(name: str | None) -> str:
    name = (name or config.WHISPER_MODEL).strip()
    if name not in config.ALLOWED_WHISPER_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Whisper model {name!r}.",
        )
    return name


def _validate_target_lang(lang: str | None) -> str:
    lang = (lang or config.TRANSLATE_TARGET_LANG).strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9-]{0,9}$", lang):
        raise HTTPException(status_code=400, detail=f"Invalid target_lang {lang!r}.")
    return lang


def _fmt_hms(seconds: float) -> str:
    """Render ``seconds`` as ``H:MM:SS`` (or ``M:SS`` for short clips)."""

    s = int(round(max(0.0, seconds)))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _set(
    job_id: str,
    *,
    status=None,
    progress=None,
    message=None,
    error=None,
    files=None,
    source_name=None,
) -> None:
    jobs_mod.update_job(
        job_id,
        status=status,
        progress=progress,
        message=message,
        error=error,
        files=files,
        source_name=source_name,
    )


def _public_files(job_id: str, *, out_dir: Path, video: Path | None) -> JobFiles:
    """Build the public ``files`` mapping returned to the browser."""

    files = JobFiles()
    if (out_dir / "subtitle_id.srt").exists():
        files.srt = f"/download/{job_id}/srt"
    if (out_dir / "transcript_id.txt").exists():
        files.txt = f"/download/{job_id}/txt"
    if (out_dir / "subtitle.vtt").exists():
        files.vtt = f"/download/{job_id}/vtt"
    if (out_dir / "subtitle.ass").exists():
        files.ass = f"/download/{job_id}/ass"
    if jobs_mod.find_original_media(job_id):
        files.original = f"/download/{job_id}/original"
    if video is not None and video.exists():
        files.video = f"/download/{job_id}/video"
    return files


def _write_all_subs(translated: list[Segment], out_dir: Path) -> None:
    """Emit SRT, TXT, VTT, ASS and the editable JSON dump in one place."""

    write_srt(translated, out_dir / "subtitle_id.srt")
    write_txt(translated, out_dir / "transcript_id.txt")
    write_vtt(translated, out_dir / "subtitle.vtt")
    write_ass(translated, out_dir / "subtitle.ass")
    write_segments_json(translated, out_dir / "segments.json")


def _process_job(job_id: str) -> None:
    """The entire pipeline for a single job. Never raises."""

    log.info("Job %s: worker thread started", job_id)
    try:
        job = jobs_mod.load_job(job_id)
        if job is None:
            log.error("Job %s vanished before processing", job_id)
            return

        out_dir = jobs_mod.job_output_dir(job_id)
        burn_path = out_dir / "video_subtitle.mp4"

        # 1. Acquire source media — either via yt-dlp or a pre-uploaded file.
        if job.source_kind == "upload":
            media_path = jobs_mod.find_original_media(job_id)
            if media_path is None:
                raise RuntimeError("Uploaded file vanished from disk.")
            _set(job_id, status="processing", progress=20, message="File received.")
        else:
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
            _set(
                job_id,
                progress=22,
                message="Media downloaded successfully…",
                source_name=media_path.name,
            )

        # 2. Audio extraction
        _set(job_id, progress=25, message="Extracting audio…")
        audio_path = extract_audio(media_path, out_dir)

        # 3. Transcribe — emit per-segment progress in the 32..65% range so
        # the UI doesn't sit at 32% for the entire (potentially long) Whisper
        # pass. Throttled to one update per ~3s and one progress percent per
        # change so we don't hammer the JSON state store.
        _set(
            job_id,
            progress=32,
            message=f"AI is creating timestamps with Whisper '{job.whisper_model}'…",
        )

        last_emit = {"t": 0.0, "pct": 32}

        def _on_seg(seg_end: float, total: float, segs_so_far: int) -> None:
            if total <= 0:
                return
            ratio = max(0.0, min(seg_end / total, 1.0))
            pct = 32 + int(ratio * (65 - 32))
            now = time.monotonic()
            if pct <= last_emit["pct"] and now - last_emit["t"] < 3.0:
                return
            last_emit["t"] = now
            last_emit["pct"] = pct
            _set(
                job_id,
                progress=pct,
                message=(
                    f"AI is transcribing… {_fmt_hms(seg_end)} / {_fmt_hms(total)}"
                    f" ({segs_so_far} segments so far)"
                ),
            )

        segments = transcribe(
            audio_path,
            model_name=job.whisper_model,
            progress_cb=_on_seg,
        )
        if not segments:
            raise RuntimeError("Transcription returned no segments. Is the audio silent?")
        _set(job_id, progress=65, message=f"Transcribed {len(segments)} segments.")

        # 4. Translate
        _set(
            job_id,
            progress=70,
            message=f"Translating subtitles to '{job.target_lang}'…",
        )
        translated = translate_segments(segments, target=job.target_lang)

        # 5. Write SRT + TXT + VTT + ASS + segments.json
        _set(job_id, progress=85, message="Generating subtitle files…")
        _write_all_subs(translated, out_dir)

        burn_out: Path | None = None
        if job.burn_video:
            _set(job_id, progress=90, message="Burning subtitle into video…")
            try:
                burn_out = burn_subtitle(
                    media_path,
                    out_dir / "subtitle_id.srt",
                    burn_path,
                    style=BurnStyle.from_dict(job.style),
                )
            except (FFmpegError, FFmpegMissing) as e:
                log.warning("Burn-in failed for %s: %s", job_id, e)
                _set(
                    job_id,
                    message=(
                        "Subtitles ready. Burn-in skipped: " + str(e).split("\n")[0][:200]
                    ),
                )

        files = _public_files(job_id, out_dir=out_dir, video=burn_out)
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
            "whisper_models": config.WHISPER_MODELS,
            "default_whisper_model": config.WHISPER_MODEL,
            "target_languages": config.TARGET_LANGUAGES,
            "default_target_lang": config.TRANSLATE_TARGET_LANG,
            "style_fonts": config.STYLE_FONTS,
            "style_positions": config.STYLE_POSITIONS,
            "style_defaults": config.STYLE_DEFAULTS,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    cfg = llm_mod.load_config()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "app_name": config.APP_NAME,
            "llm_config": cfg.to_public(),
        },
    )


@app.get("/api/llm/config")
async def llm_config_get() -> dict:
    return llm_mod.load_config().to_public()


@app.post("/api/llm/test")
async def llm_test(payload: dict) -> dict:
    """Validate Base URL + API key by listing models.

    Always returns ``200`` with ``{ok, models, error}`` so the client can
    treat connection failures as data, not exceptions. If ``api_key`` is
    omitted the saved key (if any) is used so the user can re-test without
    re-typing.
    """

    if not isinstance(payload, dict):
        return {"ok": False, "error": "Invalid request body.", "models": []}

    base_url = str(payload.get("base_url") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()

    if not base_url:
        return {"ok": False, "error": "Base URL is required.", "models": []}

    if not api_key:
        api_key = llm_mod.load_config().api_key
        if not api_key:
            return {"ok": False, "error": "API key is required.", "models": []}

    try:
        models = await llm_mod.list_models(base_url, api_key)
    except llm_mod.LLMError as e:
        return {"ok": False, "error": str(e), "models": []}
    return {"ok": True, "error": None, "models": models}


@app.put("/api/llm/config")
async def llm_config_put(payload: dict) -> dict:
    """Validate + persist LLM configuration.

    Body: ``{base_url, api_key?, model}``. The API key is optional only when
    a saved key already exists (so the user can change model/base without
    re-entering it). The endpoint validates by listing models before writing
    to disk, so an unreachable endpoint or wrong key never gets persisted.
    """

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid request body.")

    base_url = llm_mod.normalize_base_url(str(payload.get("base_url") or ""))
    api_key = str(payload.get("api_key") or "").strip()
    model = str(payload.get("model") or "").strip()

    if not base_url:
        raise HTTPException(status_code=400, detail="Base URL is required.")
    if not model:
        raise HTTPException(status_code=400, detail="Model is required.")

    saved = llm_mod.load_config()
    if not api_key:
        api_key = saved.api_key
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required.")

    try:
        models = await llm_mod.list_models(base_url, api_key)
    except llm_mod.LLMError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if model not in models:
        # Some providers don't list every model in /models (custom fine-tunes,
        # etc.). We honour the user's choice but log it for debugging.
        log.warning(
            "LLM config saved with model %r not in detected list (%d models)",
            model,
            len(models),
        )

    cfg = llm_mod.LLMConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    llm_mod.save_config(cfg)
    log.info("LLM config saved: base=%s model=%s", base_url, model)
    return {"ok": True, "config": cfg.to_public()}


def _start_worker(job_id: str) -> None:
    """Spawn a daemon thread that runs the pipeline for ``job_id``."""

    t = threading.Thread(target=_process_job, args=(job_id,), daemon=True)
    t.start()


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_filename(name: str | None) -> str:
    base = (name or "upload.mp4").strip().replace("\\", "/").rsplit("/", 1)[-1]
    base = _SAFE_FILENAME_RE.sub("_", base)
    if not base or base.startswith("."):
        base = "upload" + (Path(name or "").suffix or ".mp4")
    return base[:120]


def _save_upload(file: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _safe_filename(file.filename)
    written = 0
    with open(dest, "wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > config.MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Upload exceeds {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                    ),
                )
            out.write(chunk)
    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Empty upload.")
    return dest


@app.post("/api/jobs")
async def create_job_endpoint(
    url: str | None = Form(None),
    quality: str = Form(config.DEFAULT_QUALITY),
    burn_video: str | None = Form(None),
    target_lang: str | None = Form(None),
    whisper_model: str | None = Form(None),
    style: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict:
    """Create a new job from either a URL or a multipart file upload."""

    burn = str(burn_video).lower() in ("1", "true", "on", "yes") if burn_video else False
    quality = _validate_quality(quality)
    target_lang = _validate_target_lang(target_lang)
    whisper_model = _validate_whisper_model(whisper_model)

    style_dict: dict = {}
    if style:
        try:
            parsed = json.loads(style)
            if isinstance(parsed, dict):
                style_dict = parsed
        except json.JSONDecodeError:
            pass

    has_file = file is not None and file.filename
    has_url = bool((url or "").strip())

    if not has_file and not has_url:
        raise HTTPException(status_code=400, detail="Provide a URL or a file upload.")

    if has_file:
        # File upload path — skip yt-dlp and write the file straight into
        # the job's downloads directory so the rest of the pipeline can find
        # it via ``find_original_media``.
        job = jobs_mod.create_job(
            url="(uploaded file)",
            quality=quality,
            burn_video=burn,
            target_lang=target_lang,
            whisper_model=whisper_model,
            source_kind="upload",
            source_name=file.filename,
            style=style_dict,
        )
        try:
            saved = _save_upload(file, jobs_mod.job_download_dir(job.job_id))
        except HTTPException:
            jobs_mod.update_job(
                job.job_id,
                status="failed",
                error="Upload failed.",
                message="Upload failed.",
            )
            raise
        log.info("Job %s: received upload %s (%d bytes)", job.job_id, saved.name, saved.stat().st_size)
        _start_worker(job.job_id)
        return {"job_id": job.job_id}

    # URL path
    valid_url = _validate_url(url or "")
    job = jobs_mod.create_job(
        url=valid_url,
        quality=quality,
        burn_video=burn,
        target_lang=target_lang,
        whisper_model=whisper_model,
        source_kind="url",
        source_name=None,
        style=style_dict,
    )
    _start_worker(job.job_id)
    return {"job_id": job.job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = jobs_mod.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.get("/api/jobs/{job_id}/segments")
async def get_segments(job_id: str) -> JSONResponse:
    job = jobs_mod.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    out_dir = config.OUTPUTS_DIR / job_id
    segs = read_segments_json(out_dir / "segments.json")
    return JSONResponse({"segments": [s.to_dict() for s in segs]})


@app.put("/api/jobs/{job_id}/segments")
async def put_segments(job_id: str, payload: dict) -> dict:
    """Replace the editable segments and regenerate SRT/TXT/VTT/ASS.

    Optional ``rerender_video=True`` will also re-run the burn-in step using
    the original media. We never re-run Whisper here.
    """

    job = jobs_mod.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    raw_segs = payload.get("segments")
    if not isinstance(raw_segs, list) or not raw_segs:
        raise HTTPException(status_code=400, detail="segments[] is required.")

    parsed: list[Segment] = []
    for item in raw_segs:
        if not isinstance(item, dict):
            continue
        try:
            parsed.append(Segment.from_dict(item))
        except (KeyError, ValueError, TypeError):
            continue
    if not parsed:
        raise HTTPException(status_code=400, detail="No valid segments.")
    parsed.sort(key=lambda s: s.start)

    out_dir = config.OUTPUTS_DIR / job_id
    _write_all_subs(parsed, out_dir)

    rerender = bool(payload.get("rerender_video"))
    burn_out: Path | None = out_dir / "video_subtitle.mp4"
    if not burn_out.exists():
        burn_out = None

    if rerender and job.burn_video:
        media_path = jobs_mod.find_original_media(job_id)
        if media_path is None:
            raise HTTPException(status_code=400, detail="Original media missing; cannot re-burn.")
        try:
            burn_out = burn_subtitle(
                media_path,
                out_dir / "subtitle_id.srt",
                out_dir / "video_subtitle.mp4",
                style=BurnStyle.from_dict(job.style),
            )
        except (FFmpegError, FFmpegMissing) as e:
            raise HTTPException(status_code=500, detail=f"Re-burn failed: {e}")

    files = _public_files(job_id, out_dir=out_dir, video=burn_out)
    jobs_mod.update_job(job_id, files=files)
    return {"ok": True, "count": len(parsed), "rerender": rerender}


KindT = Literal["srt", "txt", "vtt", "ass", "original", "video"]


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
        return FileResponse(path, filename=f"{job_id}_subtitle.srt", media_type="application/x-subrip")

    if kind == "txt":
        path = out_dir / "transcript_id.txt"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Transcript not generated yet.")
        return FileResponse(path, filename=f"{job_id}_transcript.txt", media_type="text/plain")

    if kind == "vtt":
        path = out_dir / "subtitle.vtt"
        if not path.exists():
            raise HTTPException(status_code=404, detail="VTT not generated yet.")
        return FileResponse(path, filename=f"{job_id}_subtitle.vtt", media_type="text/vtt")

    if kind == "ass":
        path = out_dir / "subtitle.ass"
        if not path.exists():
            raise HTTPException(status_code=404, detail="ASS not generated yet.")
        return FileResponse(path, filename=f"{job_id}_subtitle.ass", media_type="text/x-ssa")

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
async def healthz() -> dict:
    return {
        "ok": True,
        "app": config.APP_NAME,
        "ffmpeg": "ok" if shutil.which("ffmpeg") else "missing",
    }
