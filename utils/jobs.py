"""Job lifecycle management.

A job is a JSON file under ``jobs/<job_id>.json`` plus working directories at
``downloads/<job_id>/`` and ``outputs/<job_id>/``. The status file is the
single source of truth that the API hands back to the browser.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import config

# Windows denies os.replace when another handle has the destination open
# (browser status polling, antivirus, etc.). Retry briefly before failing.
_ATOMIC_REPLACE_RETRIES = 12
_ATOMIC_REPLACE_DELAY = 0.03

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


def _is_transient_io_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        # 5 = access denied, 32 = sharing violation (Windows)
        return getattr(exc, "winerror", None) in (5, 32)
    return False


def _atomic_replace(src: Path, dest: Path) -> None:
    """Replace ``dest`` with ``src``, retrying transient Windows lock errors."""

    last_err: BaseException | None = None
    for attempt in range(_ATOMIC_REPLACE_RETRIES):
        try:
            os.replace(src, dest)
            return
        except OSError as exc:
            if not _is_transient_io_error(exc):
                raise
            last_err = exc
            time.sleep(_ATOMIC_REPLACE_DELAY * (1.4**attempt))
    if last_err is not None:
        raise last_err


def _read_text_with_retry(path: Path) -> str:
    last_err: BaseException | None = None
    for attempt in range(_ATOMIC_REPLACE_RETRIES):
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            if not _is_transient_io_error(exc):
                raise
            last_err = exc
            time.sleep(_ATOMIC_REPLACE_DELAY * (1.4**attempt))
    if last_err is not None:
        raise last_err
    raise OSError(f"Unable to read {path}")


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


def _parse_job_payload(data: dict[str, Any]) -> Job:
    files_data = data.pop("files", {}) or {}
    files = JobFiles(**{k: files_data.get(k) for k in JobFiles.__dataclass_fields__})

    # Backwards-compat: pre-feature jobs may not have these keys.
    data.setdefault("target_lang", "id")
    data.setdefault("whisper_model", "small")
    data.setdefault("source_kind", "url")
    data.setdefault("source_name", None)
    data.setdefault("style", {})

    return Job(files=files, **data)


def _load_job_unlocked(job_id: str) -> Job | None:
    path = job_status_path(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(_read_text_with_retry(path))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return _parse_job_payload(data)


def save_job(job: Job) -> None:
    path = job_status_path(job.job_id)
    tmp = path.with_suffix(".json.tmp")
    with _lock_for(job.job_id):
        tmp.write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _atomic_replace(tmp, path)


def load_job(job_id: str) -> Job | None:
    with _lock_for(job_id):
        return _load_job_unlocked(job_id)


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
        job = _load_job_unlocked(job_id)
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
