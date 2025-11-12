from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from AEGIS.src.packages.utils.services.payload import sanitize_search_payload

from AEGIS.src.packages.configurations import (
    API_SETTINGS,
    ClientRuntimeConfig,
    HTTP_SETTINGS,
)
from AEGIS.src.packages.constants import (
    CLOUD_MODEL_CHOICES,
    GEO_SEARCH_URL,
)

###############################################################################
@dataclass
class RuntimeSettings:
    use_cloud_services: bool
    provider: str
    cloud_model: str
    agent_model: str
    temperature: float | None
    reasoning: bool


# [HELPERS]
###############################################################################
# None right now


# [LLM CLIENT CONTROLLERS]
###############################################################################
def resolve_cloud_selection(
    provider: str | None, cloud_model: str | None
) -> dict[str, Any]:
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider not in CLOUD_MODEL_CHOICES:
        normalized_provider = next(iter(CLOUD_MODEL_CHOICES), "")
    models = CLOUD_MODEL_CHOICES.get(normalized_provider, [])
    normalized_model = (cloud_model or "").strip()
    if normalized_model not in models:
        normalized_model = models[0] if models else ""
    return {
        "provider": normalized_provider,
        "models": models,
        "model": normalized_model or None,
    }

# -----------------------------------------------------------------------------
def get_runtime_settings() -> RuntimeSettings:
    provider = ClientRuntimeConfig.get_llm_provider()
    selection = resolve_cloud_selection(provider, ClientRuntimeConfig.get_cloud_model())
    return RuntimeSettings(
        use_cloud_services=ClientRuntimeConfig.is_cloud_enabled(),
        provider=selection["provider"],
        cloud_model=selection["model"],
        agent_model=ClientRuntimeConfig.get_agent_model(),
        temperature=ClientRuntimeConfig.get_ollama_temperature(),
        reasoning=ClientRuntimeConfig.is_ollama_reasoning_enabled(),
    )

# -----------------------------------------------------------------------------
def reset_runtime_settings() -> RuntimeSettings:
    ClientRuntimeConfig.reset_defaults()
    return get_runtime_settings()

# -----------------------------------------------------------------------------
def apply_runtime_settings(settings: RuntimeSettings) -> RuntimeSettings:
    ClientRuntimeConfig.set_use_cloud_services(settings.use_cloud_services)
    provider = ClientRuntimeConfig.set_llm_provider(settings.provider)
    ClientRuntimeConfig.set_cloud_model(settings.cloud_model)
    agent_model = ClientRuntimeConfig.set_agent_model(settings.agent_model)

    temperature = ClientRuntimeConfig.set_ollama_temperature(settings.temperature)
    reasoning = ClientRuntimeConfig.set_ollama_reasoning(settings.reasoning)
    selection = resolve_cloud_selection(provider, ClientRuntimeConfig.get_cloud_model())
    return RuntimeSettings(
        use_cloud_services=ClientRuntimeConfig.is_cloud_enabled(),
        provider=selection["provider"],
        cloud_model=selection["model"],
        agent_model=agent_model,
        temperature=temperature,
        reasoning=reasoning,
    )

###############################################################################
# trigger function to start the location based search on button click
###############################################################################
async def trigger_search_maps(
    url: str, payload: dict[str, Any] | None = None
) -> tuple[dict[str, Any] | None, str]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_SETTINGS.timeout) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
    except httpx.RequestError as exc:
        return None, f"[ERROR] Unable to reach map service: {exc}"
    except httpx.HTTPStatusError as exc:
        detail = extract_error_detail(exc.response)
        return None, f"[ERROR] Map service error {exc.response.status_code}: {detail}"

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        return None, f"[ERROR] Invalid response received from map service: {exc}"

    if not isinstance(data, dict):
        return None, "[ERROR] Map service returned an unexpected payload."

    status_message = extract_status_message(data)
    formatted_status = f"Endpoint: {GEO_SEARCH_URL}\nStatus: {status_message.strip()}"
    return data, formatted_status

# -----------------------------------------------------------------------------
def extract_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return response.text.strip() or "Unexpected error"

    if isinstance(data, dict):
        detail = data.get("detail") or data.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return "Unexpected error"

# -----------------------------------------------------------------------------
def extract_status_message(data: dict[str, Any]) -> str:
    for key in ("status_message", "message", "detail", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Map search request submitted."

# -----------------------------------------------------------------------------
async def submit_location_search(
    geospatial_filter: Any,
    country: str | None,
    city: str | None,
    address: str | None,
    use_coordinates: bool,
    latitude: Any,
    longitude: Any,
    date: str | None,
) -> dict[str, Any | None]:
    cleaned_payload = sanitize_search_payload(
        geospatial_filter=geospatial_filter,
        country=country,
        city=city,
        address=address,
        use_coordinates=use_coordinates,
        latitude=latitude,
        longitude=longitude,
        date=date,
    )

    url = f"{API_SETTINGS.base_url}{GEO_SEARCH_URL}"
    data, message = await trigger_search_maps(url, cleaned_payload)
    normalized_message = (message or "").strip()
    return {"json": data, "message": normalized_message or None}
