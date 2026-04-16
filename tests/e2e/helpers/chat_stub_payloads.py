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


def chat_turn_map_response(session_id: int, assistant_message: str, basemap_id: str = "osm_default") -> dict[str, Any]:
    payload = dict(ROME_MAP_SESSION)
    payload["basemap"] = {**ROME_MAP_SESSION["basemap"], "id": basemap_id}
    return {
        "session_id": session_id,
        "assistant_message": assistant_message,
        "structured_intent": {"request_text": assistant_message},
        "extracted_state": {"location": {"city": "Rome", "country": "Italy"}},
        "map_session": payload,
        "tool_payload": {"execution": "map_search", "selected_overlay_ids": ["openaq_air_quality"]},
        "follow_up_required": False,
        "fallback_mode": "none",
    }


def chat_turn_clarification_response(session_id: int, message: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "assistant_message": message,
        "structured_intent": {"request_text": message},
        "extracted_state": {"location": {}},
        "map_session": None,
        "tool_payload": {"execution": "follow_up", "fallback_mode": "needs_clarification"},
        "follow_up_required": True,
        "fallback_mode": "needs_clarification",
    }


def chat_turn_text_only_response(session_id: int, message: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "assistant_message": message,
        "structured_intent": {"request_text": message},
        "extracted_state": {"location": {"landmark": "Eiffel Tower"}},
        "map_session": None,
        "tool_payload": {"execution": "location_to_coordinates"},
        "follow_up_required": False,
        "fallback_mode": "none",
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


def chat_stream_events(session_id: int, assistant_message: str, include_tool_status: bool = True) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{"event": "status", "data": {"message": "received"}}]
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
                "extracted_state": {"location": {"city": "Rome"}},
                "map_session": ROME_MAP_SESSION,
                "follow_up_required": False,
                "fallback_mode": "none",
            },
        }
    )
    return events
