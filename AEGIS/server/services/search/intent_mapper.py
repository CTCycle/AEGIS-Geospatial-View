from __future__ import annotations

from typing import Any

from AEGIS.server.configurations import server_settings


def map_structured_intent_to_location_request(
    *,
    extracted_state: dict[str, Any],
    user_message: str,
    selected_basemap_id: str | None,
    selected_overlay_ids: list[str],
    fallback_datetime: str,
) -> dict[str, Any]:
    location = extracted_state.get("location") if isinstance(extracted_state.get("location"), dict) else {}
    coordinates = (
        extracted_state.get("coordinates") if isinstance(extracted_state.get("coordinates"), dict) else {}
    )
    has_coordinates = coordinates.get("latitude") is not None and coordinates.get("longitude") is not None
    return {
        "datetime": fallback_datetime,
        "country": location.get("country"),
        "city": location.get("city"),
        "address": location.get("address") or user_message,
        "use_coordinates": has_coordinates,
        "latitude": coordinates.get("latitude"),
        "longitude": coordinates.get("longitude"),
        "filters": extracted_state.get("filters") or [],
        "overlay_ids": selected_overlay_ids,
        "basemap_id": selected_basemap_id,
        "map_size_m": server_settings.map.default_size_m,
        "image_crs": "EPSG:3857",
    }
