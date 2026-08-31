from __future__ import annotations

from copy import deepcopy
from typing import Any


E2E_CONVERSATION_ID = "conversation-e2e"


def map_overlay_instance(
    *,
    instance_id: str,
    capability_id: str,
    label: str,
    provider: str,
    overlay_type: str,
    rendering_mode: str,
    descriptor: dict[str, Any],
    opacity: float = 1.0,
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "capability_id": capability_id,
        "label": label,
        "provider": provider,
        "overlay_type": overlay_type,
        "rendering_mode": rendering_mode,
        "scope_key": "location",
        "scope": {"kind": "location", "label": "Rome, Italy"},
        "visible": True,
        "opacity": opacity,
        "render_variant": {},
        "descriptor": descriptor,
        "inspections": [],
    }


ROME_MAP_SESSION = {
    "session_id": "rome-map-session",
    "resolved_location": {
        "label": "Rome, Italy",
        "latitude": 41.9028,
        "longitude": 12.4964,
    },
    "center": {"latitude": 41.9028, "longitude": 12.4964},
    "bounds": [12.3, 41.8, 12.7, 42.0],
    "basemap_id": "osm_default",
    "viewport": {
        "center_latitude": 41.9028,
        "center_longitude": 12.4964,
        "radius_m": 5000,
    },
    "basemap": {
        "id": "osm_default",
        "label": "OpenStreetMap",
        "provider": "osm",
        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "OpenStreetMap contributors",
        "render_status": "available",
        "unavailable_reason": None,
    },
    "compliance_warnings": ["Demo alert summary for documented session."],
    "overlay_collection": {
        "collection_id": "rome-map-overlays",
        "revision": 1,
        "instances": [
            map_overlay_instance(
                instance_id="openaq_air_quality",
                capability_id="openaq_air_quality",
                label="OpenAQ Air Quality",
                provider="openaq",
                overlay_type="tile",
                rendering_mode="xyz",
                opacity=0.65,
                descriptor={
                    "layer_id": "openaq_air_quality",
                    "provider": "openaq",
                    "rendering_mode": "xyz",
                    "source_protocol": "xyz",
                    "tile_url_template": "https://example.test/openaq/{z}/{x}/{y}.png",
                    "attribution": ["OpenAQ"],
                },
            )
        ],
    },
}


###############################################################################
def _chat_turn_contract(message: str = "stub request") -> dict[str, Any]:
    return {
        "user_text": message,
        "conversation_context": {"recent_messages": [], "memory_snapshot": {}},
        "task_class": "direct_query",
        "location_signals": [],
        "normalized_action": {
            "action_id": "stub",
            "action_label": "Stub",
            "task_tags": [],
            "action_tags": [],
            "requires_location": False,
        },
        "temporal_signal": {"mode": "none"},
        "ambiguities": [],
        "disallowed_patterns": [],
        "parser_confidence": 1.0,
    }


###############################################################################
def _chat_decision(state: str = "direct_tool") -> dict[str, Any]:
    return {
        "plan": {
            "state": state,
            "action_id": "stub",
            "overlay_ids": [],
        },
        "trace": {"steps": ["stub"]},
    }


###############################################################################
def chat_completion_map_payload(
    turn_number: int, assistant_message: str, basemap_id: str = "osm_default"
) -> dict[str, Any]:
    payload = deepcopy(ROME_MAP_SESSION)
    payload["basemap"] = {**ROME_MAP_SESSION["basemap"], "id": basemap_id}
    return {
        "request_id": f"chat-stub-{turn_number}",
        "conversation_id": E2E_CONVERSATION_ID,
        "assistant_message": assistant_message,
        "turn_contract": _chat_turn_contract(),
        "decision": _chat_decision("map_search"),
        "map_session": payload,
        "tool_payload": {
            "execution": "map_search",
            "selected_overlay_ids": ["openaq_air_quality"],
        },
    }


###############################################################################
def chat_completion_clarification_payload(
    turn_number: int, message: str
) -> dict[str, Any]:
    return {
        "request_id": f"chat-stub-{turn_number}",
        "conversation_id": E2E_CONVERSATION_ID,
        "assistant_message": message,
        "turn_contract": _chat_turn_contract(),
        "decision": _chat_decision("clarify"),
        "map_session": None,
        "tool_payload": {
            "execution": "follow_up",
        },
    }


###############################################################################
def chat_completion_text_payload(turn_number: int, message: str) -> dict[str, Any]:
    return {
        "request_id": f"chat-stub-{turn_number}",
        "conversation_id": E2E_CONVERSATION_ID,
        "assistant_message": message,
        "turn_contract": _chat_turn_contract(),
        "decision": _chat_decision("direct_tool"),
        "map_session": None,
        "tool_payload": {"execution": "location_to_coordinates"},
    }


###############################################################################
def model_settings_payload() -> dict[str, Any]:
    return {
        "active_provider_mode": "local",
        "agent_model_provider": "ollama",
        "agent_model_name": "llama3.2",
        "ollama_url": "http://localhost:11434",
        "openai_base_url": None,
        "google_base_url": None,
        "deepseek_base_url": None,
        "credentials": {"openai": {"api_key": False}, "google": {"api_key": False}},
        "credential_health": {},
        "selected_model_context": {
            "provider": "ollama",
            "model": "llama3.2",
            "context_window_tokens": None,
            "maximum_output_tokens": None,
            "context_profile_source": "fixture",
        },
    }


###############################################################################
def model_catalog_payload() -> dict[str, Any]:
    return {
        "cloud": [
            {
                "id": "gpt-5-mini",
                "name": "gpt-5-mini",
                "description": "Low-latency OpenAI cloud model.",
                "provider": "openai",
                "capabilities": ["chat", "tools", "structured_output"],
                "supports_tools": True,
                "supports_structured_output": True,
                "tool_support_source": "fixture",
                "context_profile_source": "fixture",
                "metadata": {"tier": "mini"},
            },
            {
                "id": "gpt-4.1-mini",
                "name": "gpt-4.1-mini",
                "description": "General purpose OpenAI cloud model.",
                "provider": "openai",
                "capabilities": ["chat"],
                "tool_support_source": "fixture",
                "context_profile_source": "fixture",
                "metadata": {"tier": "mini"},
            },
            {
                "id": "gemini-2.5-flash",
                "name": "gemini-2.5-flash",
                "description": "Fast Google cloud model.",
                "provider": "google",
                "capabilities": ["chat"],
                "tool_support_source": "fixture",
                "context_profile_source": "fixture",
                "metadata": {"tier": "flash"},
            },
            {
                "id": "llama3.2",
                "name": "llama3.2",
                "description": "Local Ollama model available in cloud catalog.",
                "provider": "ollama",
                "capabilities": ["chat"],
                "tool_support_source": "fixture",
                "context_profile_source": "fixture",
                "metadata": {"family": "llama"},
            },
        ],
        "local": [
            {
                "id": "llama3.2",
                "name": "llama3.2",
                "description": "Installed local Ollama model.",
                "provider": "ollama",
                "capabilities": ["chat"],
                "tool_support_source": "fixture",
                "context_profile_source": "fixture",
                "metadata": {"family": "llama"},
            }
        ],
        "sources": {},
    }


###############################################################################
def selected_agent_settings_payload() -> dict[str, Any]:
    return {
        "active_provider_mode": "cloud",
        "agent_model_provider": "openai",
        "agent_model_name": "gpt-4.1-mini",
        "ollama_url": "http://localhost:11434",
        "openai_base_url": "https://api.openai.com/v1",
        "google_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "deepseek_base_url": None,
        "credentials": {"openai": {"api_key": False}, "google": {"api_key": True}},
        "credential_health": {},
        "selected_model_context": {
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "context_window_tokens": None,
            "maximum_output_tokens": None,
            "context_profile_source": "fixture",
        },
    }


###############################################################################
def _catalog_capability(
    *,
    capability_id: str,
    name: str,
    kind: str,
    capability_type: str,
    description: str,
    provider: str,
    supports_map: bool,
    supports_direct_text: bool,
    source_protocol: str,
    data_format: str,
    geometry_type: str,
    queryable: bool,
    rendering_mode: str,
    render: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": capability_id,
        "name": name,
        "kind": kind,
        "type": capability_type,
        "description": description,
        "provider": provider,
        "requires_credentials": False,
        "is_available": True,
        "supports_map": supports_map,
        "supports_direct_text": supports_direct_text,
        "coverage": "global",
        "source_protocol": source_protocol,
        "data_format": data_format,
        "geometry_type": geometry_type,
        "queryable": queryable,
        "endpoint_health": "healthy",
        "auth_mode": "none",
        "official_docs_url": "https://example.test/aegis-fixture",
        "capability_kind": kind,
        "rendering_mode": rendering_mode,
        "reliability": {
            "status": "verified",
            "last_audited": "2026-08-31",
            "known_limitations": [],
        },
        "auth": {
            "type": "none",
            "required": False,
            "provider_key": None,
            "access_page_provider_id": None,
        },
        "action_tags": [],
        "task_tags": [],
        "metadata": {},
    }
    if render is not None:
        payload["render"] = render
    return payload


###############################################################################
def geospatial_catalog_payload() -> dict[str, Any]:
    return {
        "capabilities": [
            _catalog_capability(
                capability_id="openmeteo_weather_forecast",
                name="Open-Meteo Weather Forecast",
                kind="tool",
                capability_type="direct-tool",
                description="Fixture weather forecast capability.",
                provider="openmeteo",
                supports_map=False,
                supports_direct_text=True,
                source_protocol="https",
                data_format="json",
                geometry_type="point",
                queryable=True,
                rendering_mode="metadata-only",
            )
        ],
        "providers": [
            _catalog_capability(
                capability_id="osm",
                name="OpenStreetMap",
                kind="provider",
                capability_type="map-provider",
                description="Fixture map provider.",
                provider="osm",
                supports_map=True,
                supports_direct_text=False,
                source_protocol="xyz",
                data_format="raster",
                geometry_type="none",
                queryable=False,
                rendering_mode="xyz",
            )
        ],
        "basemaps": [
            _catalog_capability(
                capability_id="osm_default",
                name="OpenStreetMap",
                kind="basemap",
                capability_type="tile",
                description="Fixture street basemap.",
                provider="osm",
                supports_map=True,
                supports_direct_text=False,
                source_protocol="xyz",
                data_format="raster",
                geometry_type="none",
                queryable=False,
                rendering_mode="xyz",
                render={
                    "status": "available",
                    "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                    "attribution": "OpenStreetMap contributors",
                },
            ),
            _catalog_capability(
                capability_id="esri_world_imagery",
                name="Esri World Imagery",
                kind="basemap",
                capability_type="tile",
                description="Fixture satellite basemap.",
                provider="esri",
                supports_map=True,
                supports_direct_text=False,
                source_protocol="xyz",
                data_format="raster",
                geometry_type="none",
                queryable=False,
                rendering_mode="xyz",
                render={
                    "status": "available",
                    "tile_url": "https://example.test/esri/{z}/{y}/{x}.jpg",
                    "attribution": "Esri",
                },
            ),
        ],
        "overlays": [
            _catalog_capability(
                capability_id="openaq_air_quality",
                name="OpenAQ Air Quality",
                kind="overlay",
                capability_type="tile",
                description="Fixture air quality overlay.",
                provider="openaq",
                supports_map=True,
                supports_direct_text=False,
                source_protocol="xyz",
                data_format="raster",
                geometry_type="none",
                queryable=False,
                rendering_mode="xyz",
                render={
                    "status": "available",
                    "tile_url": "https://example.test/openaq/{z}/{x}/{y}.png",
                    "attribution": "OpenAQ",
                },
            )
        ],
        "cameras": [],
        "transit": [],
        "tools": [],
    }


###############################################################################
def conversation_snapshot_payload(
    user_message: str = "show map at 41.9028, 12.4964",
    assistant_message: str = "Search executed successfully.",
    map_session: dict[str, Any] | None = ROME_MAP_SESSION,
) -> dict[str, Any]:
    return {
        "conversation_id": E2E_CONVERSATION_ID,
        "title": "E2E conversation",
        "context_revision": 5,
        "messages": [
            {
                "role": "user",
                "content": user_message,
                "created_at": "2026-08-31T00:00:00Z",
            },
            {
                "role": "assistant",
                "content": assistant_message,
                "created_at": "2026-08-31T00:00:01Z",
            },
        ],
        "memory_snapshot": {},
        "map_session": deepcopy(map_session) if map_session is not None else None,
        "active_run": None,
        "task_snapshot": None,
    }
