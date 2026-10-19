from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import httpx

from server.common.typing import is_json_object
from server.services.llm.transport import LLMTransportPolicy

###############################################################################
MODELS_DEV_URL = "https://models.dev/api.json"
MODELS_DEV_TTL_SECONDS = 6 * 60 * 60

# models.dev names the AI SDK package each OpenCode model is served through;
# a missing package means the OpenAI-compatible Chat Completions endpoint.
_NPM_PROTOCOLS = {
    "@ai-sdk/anthropic": "anthropic-messages",
    "@ai-sdk/openai": "openai-responses",
    "@ai-sdk/google": "google-model",
}
_DEFAULT_PROTOCOL = "openai-chat-completions"

###############################################################################
@dataclass(frozen=True)
class ModelsDevEntry:
    protocol: str
    context_tokens: int | None
    output_tokens: int | None
    accepts_images: bool

_cache: dict[str, tuple[float, dict[str, ModelsDevEntry]]] = {}
_lock = threading.Lock()

###############################################################################
def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None

###############################################################################
def _parse_entries(payload: object, provider: str) -> dict[str, ModelsDevEntry]:
    if not is_json_object(payload):
        return {}
    provider_entry = payload.get(provider)
    models = provider_entry.get("models") if is_json_object(provider_entry) else None
    if not is_json_object(models):
        return {}
    entries: dict[str, ModelsDevEntry] = {}
    for model_id, raw in models.items():
        if not is_json_object(raw):
            continue
        override = raw.get("provider")
        npm = override.get("npm") if is_json_object(override) else None
        limit = raw.get("limit")
        modalities = raw.get("modalities")
        inputs = modalities.get("input") if is_json_object(modalities) else None
        entries[model_id.strip().lower()] = ModelsDevEntry(
            protocol=_NPM_PROTOCOLS.get(str(npm), _DEFAULT_PROTOCOL),
            context_tokens=_positive_int(limit.get("context"))
            if is_json_object(limit)
            else None,
            output_tokens=_positive_int(limit.get("output"))
            if is_json_object(limit)
            else None,
            accepts_images=isinstance(inputs, list) and "image" in inputs,
        )
    return entries

###############################################################################
def fetch_models_dev_entries(
    provider: str, transport_policy: LLMTransportPolicy
) -> dict[str, ModelsDevEntry]:
    """Return models.dev's published endpoint family and limits per model.

    The catalog is advisory: any failure yields an empty mapping so the caller
    falls back to its static table. Only successful, non-empty results are cached.
    """

    now = time.monotonic()
    with _lock:
        cached = _cache.get(provider)
        if cached is not None and now - cached[0] < MODELS_DEV_TTL_SECONDS:
            return cached[1]
    try:
        response = httpx.get(MODELS_DEV_URL, **transport_policy.httpx_options("catalog"))
        response.raise_for_status()
        entries = _parse_entries(response.json(), provider)
    except Exception:
        return {}
    if entries:
        with _lock:
            _cache[provider] = (now, entries)
    return entries
