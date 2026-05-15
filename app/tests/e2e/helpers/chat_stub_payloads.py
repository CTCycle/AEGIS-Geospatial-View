from __future__ import annotations

from typing import Any


ROME_MAP_SESSION = {
    "center": {"latitude": 41.9028, "longitude": 12.4964},
    "bounds": [12.3, 41.8, 12.7, 42.0],
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


def _chat_turn_contract(message: str = "stub request") -> dict[str, Any]:
    return {
        "user_text": message,
        "conversation_context": {"recent_messages": [], "memory_snapshot": {}},
        "task_class": "direct_query",
        "location_signals": [],
        "normalized_intent": {
            "intent_id": "stub",
            "intent_label": "Stub",
            "task_tags": [],
            "intent_tags": [],
            "requires_location": False,
        },
        "temporal_signal": {"mode": "none"},
        "ambiguities": [],
        "disallowed_patterns": [],
        "parser_confidence": 1.0,
    }


def _chat_decision(state: str = "direct_tool") -> dict[str, Any]:
    return {
        "plan": {
            "state": state,
            "intent_id": "stub",
            "overlay_ids": [],
        },
        "trace": {"steps": ["stub"]},
    }


def chat_turn_map_response(
    session_id: int, assistant_message: str, basemap_id: str = "osm_default"
) -> dict[str, Any]:
    payload = dict(ROME_MAP_SESSION)
    payload["basemap"] = {**ROME_MAP_SESSION["basemap"], "id": basemap_id}
    return {
        "request_id": f"chat-stub-{session_id}",
        "session_id": session_id,
        "assistant_message": assistant_message,
        "turn_contract": _chat_turn_contract(),
        "decision": _chat_decision("map_search"),
        "map_session": payload,
        "tool_payload": {
            "execution": "map_search",
            "selected_overlay_ids": ["openaq_air_quality"],
        },
    }


def chat_turn_clarification_response(session_id: int, message: str) -> dict[str, Any]:
    return {
        "request_id": f"chat-stub-{session_id}",
        "session_id": session_id,
        "assistant_message": message,
        "turn_contract": _chat_turn_contract(),
        "decision": _chat_decision("clarify"),
        "map_session": None,
        "tool_payload": {
            "execution": "follow_up",
        },
    }


def chat_turn_text_only_response(session_id: int, message: str) -> dict[str, Any]:
    return {
        "request_id": f"chat-stub-{session_id}",
        "session_id": session_id,
        "assistant_message": message,
        "turn_contract": _chat_turn_contract(),
        "decision": _chat_decision("direct_tool"),
        "map_session": None,
        "tool_payload": {"execution": "location_to_coordinates"},
    }


def model_settings_payload() -> dict[str, Any]:
    return {
        "active_provider_mode": "local",
        "chat_model_provider": "ollama",
        "chat_model_name": "llama3.2",
        "parser_model_provider": "ollama",
        "parser_model_name": "llama3.2",
        "agent_model_provider": "ollama",
        "agent_model_name": "llama3.2",
        "ollama_url": "http://localhost:11434",
        "openai_base_url": None,
        "google_base_url": None,
        "credentials": {"openai": {"api_key": False}, "google": {"api_key": False}},
    }


def model_catalog_payload() -> dict[str, Any]:
    return {
        "cloud": [
            {
                "id": "gpt-5-mini",
                "name": "gpt-5-mini",
                "description": "Low-latency OpenAI cloud model.",
                "provider": "openai",
                "capabilities": ["chat", "tool_use"],
                "metadata": {"tier": "mini"},
            },
            {
                "id": "gpt-4.1-mini",
                "name": "gpt-4.1-mini",
                "description": "General purpose OpenAI cloud model.",
                "provider": "openai",
                "capabilities": ["chat"],
                "metadata": {"tier": "mini"},
            },
            {
                "id": "gemini-2.5-flash",
                "name": "gemini-2.5-flash",
                "description": "Fast Google cloud model.",
                "provider": "google",
                "capabilities": ["chat"],
                "metadata": {"tier": "flash"},
            },
            {
                "id": "llama3.2",
                "name": "llama3.2",
                "description": "Local Ollama model available in cloud catalog.",
                "provider": "ollama",
                "capabilities": ["chat"],
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
                "metadata": {"family": "llama"},
            }
        ],
    }


def split_role_settings_payload() -> dict[str, Any]:
    return {
        "active_provider_mode": "cloud",
        "chat_model_provider": "openai",
        "chat_model_name": "gpt-4.1-mini",
        "parser_model_provider": "google",
        "parser_model_name": "gemini-2.5-flash",
        "agent_model_provider": "ollama",
        "agent_model_name": "llama3.2",
        "ollama_url": "http://localhost:11434",
        "openai_base_url": "https://api.openai.com/v1",
        "google_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "credentials": {"openai": {"api_key": False}, "google": {"api_key": True}},
    }


def chat_stream_events(
    session_id: int, assistant_message: str, include_tool_status: bool = True
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {"event": "status", "data": {"message": "received"}}
    ]
    for token in assistant_message.split():
        events.append({"event": "assistant_delta", "data": {"delta": f"{token} "}})
    if include_tool_status:
        events.append(
            {
                "event": "tool_status",
                "data": {
                    "available": True,
                    "execution": "map_search",
                    "has_satellite_imagery": False,
                    "has_map_session": True,
                    "overlay_count": 1,
                },
            }
        )
    events.append(
        {
            "event": "final",
            "data": {
                "session_id": session_id,
                "assistant_message": assistant_message,
                "map_session": ROME_MAP_SESSION,
            },
        }
    )
    return events
