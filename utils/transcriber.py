"""faster-whisper wrapper.

Models are loaded lazily and cached process-wide *per model name* so a long
running server doesn't pay the load cost for each job. Defaults are
CPU-friendly so SublyAI can run on a tiny VPS without a GPU. The user can
pick a different model size per job in the UI; the first job for each new
size will pay the download/load cost once and the result is cached.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from faster_whisper import WhisperModel

import config

log = logging.getLogger(__name__)


@dataclass
class Segment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(start=float(d["start"]), end=float(d["end"]), text=str(d.get("text") or ""))


_model_lock = threading.Lock()
_models: dict[str, WhisperModel] = {}


def _get_model(name: str) -> WhisperModel:
    """Return a cached WhisperModel for ``name`` (loading it on first use)."""

    with _model_lock:
        m = _models.get(name)
        if m is not None:
            return m
        log.info(
            "Loading Whisper model %s (device=%s, compute=%s)",
            name,
            config.WHISPER_DEVICE,
            config.WHISPER_COMPUTE_TYPE,
        )
        m = WhisperModel(
            name,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
        _models[name] = m
        return m


# Type alias: ``progress_cb(seg_end_seconds, total_seconds, segments_so_far)``.
ProgressCB = Callable[[float, float, int], None]


def transcribe(
    audio_path: Path,
    model_name: str | None = None,
    progress_cb: Optional[ProgressCB] = None,
) -> list[Segment]:
    """Return ordered timestamped segments for the given audio file.

    ``model_name`` overrides the default Whisper model size; falls back to the
    one configured via ``SUBLYAI_WHISPER_MODEL`` (or "small").

    If ``progress_cb`` is provided it is invoked once per yielded segment with
    ``(seg_end_seconds, total_audio_seconds, segments_so_far)`` so a caller
    can stream progress updates while Whisper iterates over the audio.
    Exceptions raised by the callback are logged and ignored — they must
    never block transcription.
    """

    name = model_name or config.WHISPER_MODEL
    model = _get_model(name)
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    total = float(getattr(info, "duration", 0.0) or 0.0)
    out: list[Segment] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if text:
            out.append(Segment(start=float(seg.start), end=float(seg.end), text=text))
        if progress_cb is not None:
            try:
                progress_cb(float(seg.end), total, len(out))
            except Exception:  # pragma: no cover - never block on UI updates
                log.exception("transcribe progress_cb raised; ignoring")
    return out
