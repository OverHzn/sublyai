"""Translate Whisper segments into Bahasa Indonesia.

We never want a translation failure to fail the whole job, so any error per
segment falls back to the original text.
"""

from __future__ import annotations

import logging
from typing import Iterable

from deep_translator import GoogleTranslator

import config
from utils.transcriber import Segment

log = logging.getLogger(__name__)


def translate_segments(
    segments: Iterable[Segment],
    target: str = config.TRANSLATE_TARGET_LANG,
) -> list[Segment]:
    """Return new Segments with translated text, preserving order/timestamps."""

    translator = GoogleTranslator(source="auto", target=target)
    out: list[Segment] = []
    for seg in segments:
        translated = seg.text
        try:
            result = translator.translate(seg.text)
            if result:
                translated = result.strip()
        except Exception as e:  # noqa: BLE001 - keep the job alive
            log.warning("Translate failed for segment, keeping original: %s", e)
        out.append(Segment(start=seg.start, end=seg.end, text=translated))
    return out
