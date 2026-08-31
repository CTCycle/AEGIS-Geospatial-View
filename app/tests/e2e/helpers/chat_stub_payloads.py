from __future__ import annotations

from typing import Any


E2E_CONVERSATION_ID = "conversation-e2e"

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
    "overlay_ids": ["openaq_air_quality"],
    "viewport": {
        "center_latitude": 41.9028,
        "center_longitude": 12.4964,
        "radius_m": 5000,
    },
    "basemap": {
        "id": "osm_default",
        "label": "OpenStreetMap",
        "provider": "osm",
        "type": "tile",
        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "requires_key": False,
    },
    "overlays": [
        {
            "id": "openaq_air_quality",
            "label": "OpenAQ Air Quality",
            "provider": "openaq",
            "type": "tile",
            "url": "https://example.test/openaq/{z}/{x}/{y}.png",
            "default_opacity": 0.65,
            "requires_key": False,
        }
    ],
    "compliance_warnings": ["Demo alert summary for documented session."],
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
    payload = dict(ROME_MAP_SESSION)
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
def geospatial_catalog_payload() -> dict[str, Any]:
    return {
        "capabilities": [],
        "providers": [],
        "basemaps": [],
        "overlays": [],
        "cameras": [],
        "transit": [],
        "tools": [],
    }


###############################################################################
