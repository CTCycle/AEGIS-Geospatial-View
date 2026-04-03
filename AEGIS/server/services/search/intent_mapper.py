from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from AEGIS.server.configurations import server_settings


def map_structured_intent_to_location_request(intent: dict[str, Any]) -> dict[str, Any]:
    coordinates = intent.get("coordinates") if isinstance(intent.get("coordinates"), dict) else {}
    datetime_value = intent.get("datetime")
    if not datetime_value:
        datetime_value = datetime.now(UTC).isoformat()
    return {
        "datetime": datetime_value,
        "time_of_day": intent.get("time_of_day"),
        "timeline_year": intent.get("timeline_year"),
        "country": intent.get("country"),
        "city": intent.get("city"),
        "address": intent.get("location") or intent.get("location_text"),
        "use_coordinates": bool(coordinates),
        "latitude": coordinates.get("latitude", intent.get("latitude")),
        "longitude": coordinates.get("longitude", intent.get("longitude")),
        "filters": list(intent.get("filters") or []),
        "overlay_ids": list(intent.get("requested_overlays") or intent.get("overlay_ids") or []),
        "basemap_id": intent.get("base_map") or intent.get("basemap_id"),
        "bbox": intent.get("bbox"),
        "radius_m": float(intent.get("radius_m") or intent.get("search_radius_m") or 2500.0),
        "image_crs": intent.get("image_crs") or "EPSG:3857",
        "map_tiles": intent.get("map_tiles") or server_settings.map.tiles,
    }
