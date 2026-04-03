from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from AEGIS.server.configurations import server_settings
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.geospatial.overlay_translation import (
    translate_overlay_ids_to_filters,
)


def map_structured_intent_to_location_request(intent: dict[str, Any]) -> dict[str, Any]:
    location = intent.get("location") if isinstance(intent.get("location"), dict) else {}
    display_area = intent.get("display_area") if isinstance(intent.get("display_area"), dict) else {}
    overlays_block = intent.get("overlays") if isinstance(intent.get("overlays"), dict) else {}
    coordinates = location.get("coordinates") if isinstance(location.get("coordinates"), dict) else {}
    datetime_value = intent.get("datetime")
    planning = intent.get("planning") if isinstance(intent.get("planning"), dict) else {}
    if not datetime_value:
        datetime_value = planning.get("datetime_inference") or datetime.now(UTC).isoformat()
    overlay_ids = list(overlays_block.get("requested") or intent.get("requested_overlays") or intent.get("overlay_ids") or [])
    manifests = GeospatialManifestLoader().load_all()
    compatibility_filters = translate_overlay_ids_to_filters(overlay_ids, manifests.get("overlays", []))
    bbox = display_area.get("bbox") or location.get("bbox") or intent.get("bbox")
    radius_value = display_area.get("radius_m") or intent.get("radius_m") or intent.get("search_radius_m") or 2500.0
    map_size_m = display_area.get("map_size_m")
    return {
        "datetime": datetime_value,
        "time_of_day": intent.get("time_of_day"),
        "timeline_year": intent.get("timeline_year"),
        "country": intent.get("country"),
        "city": intent.get("city"),
        "address": location.get("text") or intent.get("location") or intent.get("location_text"),
        "use_coordinates": bool(coordinates),
        "latitude": coordinates.get("latitude", intent.get("latitude")),
        "longitude": coordinates.get("longitude", intent.get("longitude")),
        "filters": compatibility_filters,
        "overlay_ids": overlay_ids,
        "basemap_id": intent.get("base_map") or intent.get("basemap_id"),
        "bbox": bbox,
        "radius_m": float(radius_value),
        "map_size_m": float(map_size_m) if map_size_m is not None else server_settings.map.default_size_m,
        "image_crs": intent.get("image_crs") or "EPSG:3857",
        "map_tiles": intent.get("map_tiles") or server_settings.map.tiles,
    }
