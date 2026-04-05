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
    map_preferences = intent.get("map_preferences") if isinstance(intent.get("map_preferences"), dict) else {}
    coordinates = location.get("coordinates") if isinstance(location.get("coordinates"), dict) else {}
    datetime_value = intent.get("datetime")
    planning = intent.get("planning") if isinstance(intent.get("planning"), dict) else {}
    if not datetime_value:
        temporal = intent.get("temporal_context") if isinstance(intent.get("temporal_context"), dict) else {}
        datetime_value = temporal.get("normalized_datetime") or datetime.now(UTC).isoformat()
    overlay_ids = list(map_preferences.get("overlay_candidates") or intent.get("requested_overlays") or intent.get("overlay_ids") or [])
    manifests = GeospatialManifestLoader().load_all()
    compatibility_filters = translate_overlay_ids_to_filters(overlay_ids, manifests.get("overlays", []))
    bbox = location.get("bbox") or intent.get("bbox")
    radius_value = intent.get("radius_m") or intent.get("search_radius_m") or 2500.0
    map_size_m = intent.get("map_size_m")
    basemap_id = intent.get("base_map") or intent.get("basemap_id") or map_preferences.get("basemap_preference")
    map_tiles = _resolve_map_tiles_from_basemap(manifests.get("basemaps", []), basemap_id)
    return {
        "datetime": datetime_value,
        "time_of_day": intent.get("time_of_day"),
        "timeline_year": intent.get("timeline_year"),
        "country": intent.get("country"),
        "city": intent.get("city"),
        "address": location.get("name") or location.get("text") or intent.get("location") or intent.get("location_text"),
        "use_coordinates": bool(coordinates),
        "latitude": coordinates.get("latitude", intent.get("latitude")),
        "longitude": coordinates.get("longitude", intent.get("longitude")),
        "filters": compatibility_filters,
        "overlay_ids": overlay_ids,
        "basemap_id": basemap_id,
        "bbox": bbox,
        "radius_m": float(radius_value),
        "map_size_m": float(map_size_m) if map_size_m is not None else server_settings.map.default_size_m,
        "image_crs": intent.get("image_crs") or "EPSG:3857",
        "map_tiles": intent.get("map_tiles") or map_tiles or server_settings.map.tiles,
    }


def _resolve_map_tiles_from_basemap(basemaps: list[dict[str, Any]], basemap_id: str | None) -> str | None:
    selected = basemap_id or "osm_default"
    for item in basemaps:
        if str(item.get("id")) != selected:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        tile_url = metadata.get("tile_url")
        if isinstance(tile_url, str) and tile_url.strip():
            return "OpenStreetMap" if selected == "osm_default" else tile_url
    if selected == "osm_default":
        return "OpenStreetMap"
    return None
