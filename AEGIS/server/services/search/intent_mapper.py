from __future__ import annotations

from typing import Any

from AEGIS.server.configurations import get_server_settings


def map_structured_intent_to_location_request(
    *,
    extracted_state: dict[str, Any],
    user_message: str,
    selected_basemap_id: str | None,
    selected_overlay_ids: list[str],
    fallback_datetime: str,
) -> dict[str, Any]:
    normalized_message = user_message.lower()
    location = extracted_state.get("location") if isinstance(extracted_state.get("location"), dict) else {}
    coordinates = (
        extracted_state.get("coordinates") if isinstance(extracted_state.get("coordinates"), dict) else {}
    )
    location_type = str(extracted_state.get("location_type") or location.get("location_type") or "").strip().lower() or None
    semantic_filters = extracted_state.get("filters") if isinstance(extracted_state.get("filters"), list) else []
    selected_overlay_filters = [str(value) for value in selected_overlay_ids if isinstance(value, str)]
    layer_filters = [value for value in selected_overlay_filters if value.lower().startswith("gibs_")]
    has_coordinates = coordinates.get("latitude") is not None and coordinates.get("longitude") is not None
    nearby_requested = any(token in normalized_message for token in ("nearby", "around", "area nearby", "around it"))
    default_size = float(get_server_settings().map.default_size_m)
    map_size_m = default_size
    radius_m = 2500.0
    if location_type in {"poi", "address", "coordinates"} or has_coordinates:
        map_size_m = min(default_size, 4000.0)
        radius_m = 1500.0
    if nearby_requested:
        map_size_m = min(default_size, 5000.0)
        radius_m = 2200.0
    return {
        "datetime": fallback_datetime,
        "country": location.get("country"),
        "city": location.get("city"),
        "address": location.get("address"),
        "use_coordinates": has_coordinates,
        "latitude": coordinates.get("latitude"),
        "longitude": coordinates.get("longitude"),
        "filters": layer_filters,
        "semantic_filters": semantic_filters,
        "overlay_ids": selected_overlay_ids,
        "basemap_id": selected_basemap_id,
        "map_size_m": map_size_m,
        "radius_m": radius_m,
        "image_crs": "EPSG:3857",
    }
