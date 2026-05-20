"""LLM (OpenAI-compatible) configuration + client.

Stores a single global config — base URL, API key, and selected default model
— in ``config/llm.json``. The /api/llm/* endpoints call into this module to
list models against ``GET {base_url}/models`` and to persist a validated
configuration. Nothing here actually invokes an LLM yet; this is the
foundation other features can build on.

Design notes:

- The config file is written atomically (write to .tmp, then rename) under a
  per-process RLock, and the persisted file is chmod 0600 so the API key
  doesn't leak via filesystem permissions.
- ``LLMConfig.to_public()`` deliberately omits the raw API key. Callers that
  need to show the key in the UI receive a masked preview only.
- Errors surfaced from upstream are mapped to short, user-friendly strings.
  The settings page renders them verbatim, so they should never include
  stack traces or implementation detail.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from typing import Any

import httpx

import config

log = logging.getLogger(__name__)

_lock = threading.RLock()


class LLMError(RuntimeError):
    """Raised when the configured LLM endpoint cannot be reached or refuses."""


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    updated_at: str = ""

    def to_public(self) -> dict[str, Any]:
        """Return a JSON-safe dict that NEVER includes the full api key."""

        return {
            "base_url": self.base_url,
            "model": self.model,
            "has_api_key": bool(self.api_key),
            "api_key_preview": mask_api_key(self.api_key),
            "updated_at": self.updated_at,
        }


def mask_api_key(api_key: str) -> str:
    """Return a UI-safe preview of an API key: ``••••••<last4>``."""

    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "••••"
    return f"••••••{api_key[-4:]}"


def normalize_base_url(base_url: str) -> str:
    """Strip whitespace and the trailing slash so we can append paths cleanly."""

    return (base_url or "").strip().rstrip("/")


def load_config() -> LLMConfig:
    """Load the persisted LLM config or return an empty one."""

    path = config.LLM_CONFIG_FILE
    if not path.exists():
        return LLMConfig()
    try:
        with _lock:
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Could not read LLM config; returning defaults")
        return LLMConfig()
    if not isinstance(data, dict):
        return LLMConfig()
    return LLMConfig(
        base_url=str(data.get("base_url") or ""),
        api_key=str(data.get("api_key") or ""),
        model=str(data.get("model") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


def save_config(cfg: LLMConfig) -> None:
    """Atomically write ``cfg`` to disk with restrictive permissions."""

    path = config.LLM_CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with _lock:
        tmp.write_text(
            json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        # Restrict permissions so the API key isn't world-readable on disk.
        # Some filesystems (CIFS, certain bind mounts) reject chmod; ignore.
        try:
            os.chmod(path, 0o600)
        except OSError:
            log.debug("chmod 0600 on %s failed; continuing", path)


# -- Upstream API ------------------------------------------------------------

async def list_models(base_url: str, api_key: str) -> list[str]:
    """Fetch ``GET {base_url}/models`` and return sorted model IDs.

    Raises ``LLMError`` with a short, human-friendly message if anything goes
    wrong — timeouts, DNS, TLS, auth, malformed JSON. The settings page
    renders that message verbatim, so it must stay user-facing.
    """

    base = normalize_base_url(base_url)
    if not base:
        raise LLMError("Base URL is required.")
    if not api_key:
        raise LLMError("API key is required.")

    url = f"{base}/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config.LLM_REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException as e:
        raise LLMError(
            f"Request timed out after {config.LLM_REQUEST_TIMEOUT:g}s. "
            "Check the Base URL or network connectivity."
        ) from e
    except httpx.ConnectError as e:
        raise LLMError(
            f"Could not connect to {base}. Check the Base URL and your network."
        ) from e
    except httpx.InvalidURL as e:
        raise LLMError(f"Invalid Base URL: {e}") from e
    except httpx.HTTPError as e:
        raise LLMError(f"Connection failed: {e}") from e

    if resp.status_code == 401:
        raise LLMError("Authentication failed. Check your API key.")
    if resp.status_code == 403:
        raise LLMError(
            "Access denied. The API key may not have permission to list models."
        )
    if resp.status_code == 404:
        raise LLMError(
            f"No /models endpoint at {base}. Make sure the Base URL is correct "
            "(e.g. https://api.openai.com/v1)."
        )
    if resp.status_code == 429:
        raise LLMError("Rate-limited by the provider. Wait a moment and try again.")
    if resp.status_code >= 500:
        raise LLMError(
            f"Provider returned {resp.status_code}. Try again later."
        )
    if resp.status_code >= 400:
        raise LLMError(
            f"Request failed ({resp.status_code}): {_extract_error(resp.text)}"
        )

    try:
        payload = resp.json()
    except json.JSONDecodeError as e:
        raise LLMError(
            "Response was not valid JSON. Is this an OpenAI-compatible endpoint?"
        ) from e

    items: list[Any]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        items = payload["data"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise LLMError(
            "Unexpected response shape. Expected {'data': [...]} from /models."
        )

    models: list[str] = []
    for item in items:
        if isinstance(item, dict):
            mid = item.get("id") or item.get("name")
            if mid:
                models.append(str(mid))
        elif isinstance(item, str):
            models.append(item)

    if not models:
        raise LLMError("Endpoint returned no models.")

    return sorted(set(models))


def _extract_error(body: str) -> str:
    """Best-effort extraction of a human-readable error from a JSON body."""

    body = (body or "").strip()
    if not body:
        return "(no response body)"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:200]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("type") or body[:200])
        if isinstance(err, str):
            return err
        msg = data.get("message")
        if isinstance(msg, str):
            return msg
    return body[:200]
