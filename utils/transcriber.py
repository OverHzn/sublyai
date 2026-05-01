"""faster-whisper wrapper.

The model is loaded lazily and cached process-wide so a long-running server
doesn't pay the load cost on every job. Defaults are CPU-friendly so SublyAI
can run on a tiny VPS without a GPU.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

import config

log = logging.getLogger(__name__)


@dataclass
class Segment:
    start: float
    end: float
    text: str


_model_lock = threading.Lock()
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    with _model_lock:
        if _model is None:
            log.info(
                "Loading Whisper model %s (device=%s, compute=%s)",
                config.WHISPER_MODEL,
                config.WHISPER_DEVICE,
                config.WHISPER_COMPUTE_TYPE,
            )
            _model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
        return _model


def transcribe(audio_path: Path) -> list[Segment]:
    """Return ordered timestamped segments for the given audio file."""

    model = _get_model()
    segments_iter, _info = model.transcribe(
        str(audio_path),
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    out: list[Segment] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        out.append(Segment(start=float(seg.start), end=float(seg.end), text=text))
    return out
