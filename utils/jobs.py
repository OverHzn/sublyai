"""Job lifecycle management.

A job is a JSON file under ``jobs/<job_id>.json`` plus working directories at
``downloads/<job_id>/`` and ``outputs/<job_id>/``. The status file is the
single source of truth that the API hands back to the browser.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import config

_JOB_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(job_id: str) -> threading.RLock:
    """Return a reentrant per-job lock."""

    with _LOCKS_GUARD:
        lock = _JOB_LOCKS.get(job_id)
        if lock is None:
            lock = threading.RLock()
            _JOB_LOCKS[job_id] = lock
        return lock


@dataclass
class JobFiles:
    """Map of generated artifact kinds to public download paths."""

    srt: str | None = None
    txt: str | None = None
    vtt: str | None = None
    ass: str | None = None
    original: str | None = None
    video: str | None = None


@dataclass
class Job:
    job_id: str
    url: str
    quality: str
    burn_video: bool
    target_lang: str = "id"
    whisper_model: str = "small"
    source_kind: str = "url"  # "url" or "upload"
    source_name: str | None = None  # filename for uploads, video title for URL
    style: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"  # queued | processing | done | failed
    progress: int = 0
    message: str = "Queued."
    error: str | None = None
    files: JobFiles = field(default_factory=JobFiles)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def job_status_path(job_id: str) -> Path:
    return config.JOBS_DIR / f"{job_id}.json"


def job_download_dir(job_id: str) -> Path:
    p = config.DOWNLOADS_DIR / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def job_output_dir(job_id: str) -> Path:
    p = config.OUTPUTS_DIR / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def create_job(
    *,
    url: str,
    quality: str,
    burn_video: bool,
    target_lang: str = "id",
    whisper_model: str = "small",
    source_kind: str = "url",
    source_name: str | None = None,
    style: dict[str, Any] | None = None,
) -> Job:
    job = Job(
        job_id=new_job_id(),
        url=url,
        quality=quality,
        burn_video=burn_video,
        target_lang=target_lang,
        whisper_model=whisper_model,
        source_kind=source_kind,
        source_name=source_name,
        style=style or {},
    )
    job_download_dir(job.job_id)
    job_output_dir(job.job_id)
    save_job(job)
    return job


def save_job(job: Job) -> None:
    path = job_status_path(job.job_id)
    tmp = path.with_suffix(".json.tmp")
    with _lock_for(job.job_id):
        tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2))
        tmp.replace(path)


def load_job(job_id: str) -> Job | None:
    path = job_status_path(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    files_data = data.pop("files", {}) or {}
    files = JobFiles(**{k: files_data.get(k) for k in JobFiles.__dataclass_fields__})

    # Backwards-compat: pre-feature jobs may not have these keys.
    data.setdefault("target_lang", "id")
    data.setdefault("whisper_model", "small")
    data.setdefault("source_kind", "url")
    data.setdefault("source_name", None)
    data.setdefault("style", {})

    return Job(files=files, **data)


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    error: str | None = None,
    files: JobFiles | None = None,
    source_name: str | None = None,
) -> Job | None:
    """Atomically update a subset of fields on the on-disk job record."""

    with _lock_for(job_id):
        job = load_job(job_id)
        if job is None:
            return None
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(100, int(progress)))
        if message is not None:
            job.message = message
        if error is not None:
            job.error = error
        if files is not None:
            job.files = files
        if source_name is not None:
            job.source_name = source_name
        save_job(job)
        return job


def find_original_media(job_id: str) -> Path | None:
    """Return newest media file under downloads/<job_id>/ or None."""

    folder = config.DOWNLOADS_DIR / job_id
    if not folder.exists():
        return None
    candidates: list[Path] = []
    for ext in config.ORIGINAL_MEDIA_EXTS:
        candidates.extend(folder.glob(f"*{ext}"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]
