from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from AEGIS.src.packages.configurations import (    
    ClientSettings,
    client_settings,
    server_settings    
)

from AEGIS.src.client.models import LLMRuntimeState
from AEGIS.src.packages.constants import CLOUD_MODEL_CHOICES, GEO_SEARCH_URL
from AEGIS.src.packages.utils.services.geospatial.maps import get_map_tile_options
from AEGIS.src.packages.utils.services.payload import sanitize_search_payload


# [RUNTIME SETTINGS DATACLASS]
###############################################################################
@dataclass
class RuntimeSettings:
    use_cloud_services: bool
    provider: str
    cloud_model: str
    agent_model: str
    temperature: float | None
    reasoning: bool
    map_tiles: str


# [SETTINGS]
###############################################################################
class SettingsService:
    def __init__(
        self,
        runtime_state: LLMRuntimeState | None = None,
        config: ClientSettings = client_settings,
    ) -> None:        
        self.runtime_state = runtime_state or LLMRuntimeState(config.llm_defaults)
        self.map_tiles = self.resolve_map_tiles(server_settings.map.tiles)

    # -------------------------------------------------------------------------
    def resolve_cloud_selection(
        self, provider: str | None, cloud_model: str | None
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
    
    # -------------------------------------------------------------------------
    def get_map_tile_options(self) -> tuple[dict[str, str], str]:
        default_tiles = server_settings.map.tiles or "OpenStreetMap"
        options = get_map_tile_options(default_tiles)
        return options, default_tiles

    # -------------------------------------------------------------------------
    def resolve_map_tiles(self, selection: str | None) -> str:
        options, default_tiles = self.get_map_tile_options()
        candidate = (selection or "").strip()
        if candidate:
            for choice in options:
                if candidate.lower() == choice.lower():
                    self.map_tiles = choice
                    return choice
        self.map_tiles = default_tiles
        return default_tiles

    # -------------------------------------------------------------------------    
    def get_runtime_settings(self) -> RuntimeSettings:
        selection = self.resolve_cloud_selection(
            self.runtime_state.llm_provider,
            self.runtime_state.cloud_model,
        )
        return RuntimeSettings(
            use_cloud_services=self.runtime_state.use_cloud_services,
            provider=selection["provider"],
            cloud_model=selection["model"] or "",
            agent_model=self.runtime_state.agent_model,
            temperature=self.runtime_state.ollama_temperature,
            reasoning=self.runtime_state.ollama_reasoning,
            map_tiles=self.map_tiles,
        )

    # -------------------------------------------------------------------------
    def reset_runtime_settings(self) -> RuntimeSettings:
        self.runtime_state.reset_defaults()
        self.map_tiles = self.resolve_map_tiles(server_settings.map.tiles)
        return self.get_runtime_settings()

    # -------------------------------------------------------------------------
    def apply_runtime_settings(self, settings: RuntimeSettings) -> RuntimeSettings:           
        agent_model = self.runtime_state.set_agent_model(settings.agent_model)
        temperature = self.runtime_state.set_ollama_temperature(settings.temperature)
        reasoning = self.runtime_state.set_ollama_reasoning(settings.reasoning)
        self.map_tiles = self.resolve_map_tiles(settings.map_tiles)
        
        return RuntimeSettings(
            use_cloud_services=self.runtime_state.is_cloud_enabled(),
            provider=self.runtime_state.set_llm_provider(settings.provider),
            cloud_model=self.runtime_state.get_cloud_model(),
            agent_model=agent_model,
            temperature=temperature,
            reasoning=reasoning,
            map_tiles=self.map_tiles,
        )


# [GEOSEARCH CONTROLLER]
###############################################################################
class GeoSearchEndpointService:
    def __init__(self, config: ClientSettings = client_settings) -> None:
        self.config = config

    # -------------------------------------------------------------------------
    async def trigger_search_maps(
        self, url: str, payload: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        try:
            async with httpx.AsyncClient(timeout=self.config.ui.http_timeout) as client:
                response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.RequestError as exc:
            return None, f"[ERROR] Unable to reach map service: {exc}"
        except httpx.HTTPStatusError as exc:
            detail = self.extract_error_detail(exc.response)
            return (
                None,
                f"[ERROR] Map service error {exc.response.status_code}: {detail}",
            )

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            return None, f"[ERROR] Invalid response received from map service: {exc}"

        if not isinstance(data, dict):
            return None, "[ERROR] Map service returned an unexpected payload."

        status_message = self.extract_status_message(data)
        formatted_status = (
            f"Endpoint: {GEO_SEARCH_URL}\nStatus: {status_message.strip()}"
        )
        return data, formatted_status

    # -------------------------------------------------------------------------
    def extract_error_detail(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except json.JSONDecodeError:
            return response.text.strip() or "Unexpected error"

        if isinstance(data, dict):
            detail = data.get("detail") or data.get("message")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
        return "Unexpected error"

    # -------------------------------------------------------------------------
    def extract_status_message(self, data: dict[str, Any]) -> str:
        for key in ("status_message", "message", "detail", "status"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "Map search request submitted."

    # -------------------------------------------------------------------------
    async def submit_location_search(
        self,
        geospatial_filters: list[str],
        map_tiles: str | None,
        country: str | None,
        city: str | None,
        address: str | None,
        use_coordinates: bool,
        latitude: Any,
        longitude: Any,
        date: str | None,
        agentic_enabled: bool,
    ) -> dict[str, Any | None]:
        cleaned_payload = sanitize_search_payload(
            geospatial_filters=geospatial_filters,
            map_tiles=map_tiles,
            country=country,
            city=city,
            address=address,
            use_coordinates=use_coordinates,
            latitude=latitude,
            longitude=longitude,
            date=date,
            agentic_enabled=agentic_enabled,
        )

        url = f"{self.config.ui.api_base_url}{GEO_SEARCH_URL}"
        data, message = await self.trigger_search_maps(url, cleaned_payload)
        normalized_message = (message or "").strip()
        return {"json": data, "message": normalized_message or None}
