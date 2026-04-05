from __future__ import annotations

from datetime import datetime, time
from typing import Any

from AEGIS.server.configurations import server_settings
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.utils.constants import MAP_SEARCH_STATUS_MESSAGE


def build_request_context(
    *,
    country: str | None,
    city: str | None,
    address: str | None,
    longitude: float | None,
    latitude: float | None,
    geospatial_layers: list[str],
    overlay_ids: list[str],
    basemap_id: str | None,
    map_tiles: str | None,
) -> dict[str, Any]:
    return {
        "user": None,
        "country": country,
        "city": city,
        "address": address,
        "longitude": longitude,
        "latitude": latitude,
        "geospatial_layers": list(geospatial_layers),
        "overlay_ids": list(overlay_ids),
        "basemap_id": basemap_id,
        "map_tiles": map_tiles or server_settings.map.tiles,
    }


def build_location_search_payload_data(
    *,
    datetime_value: datetime | str | None,
    time_of_day: time | str | None,
    timeline_year: int | None,
    country: str | None,
    city: str | None,
    address: str | None,
    use_coordinates: bool,
    latitude: float | None,
    longitude: float | None,
    geospatial_layers: list[str],
    basemap_id: str | None,
    overlay_ids: list[str],
    aoi: dict[str, Any] | None,
    commute: dict[str, Any] | None,
    bbox: list[float] | None,
    radius_m: float | None,
    map_size_m: float | None,
    map_tiles: str,
    image_crs: str | None,
    image_format: str | None,
) -> dict[str, Any]:
    resolved_tiles = _resolve_tiles_from_basemap(basemap_id) or map_tiles or server_settings.map.tiles
    payload_data: dict[str, Any] = {
        "datetime": datetime_value,
        "time_of_day": time_of_day,
        "timeline_year": timeline_year,
        "country": country,
        "city": city,
        "address": address,
        "use_coordinates": use_coordinates,
        "latitude": latitude,
        "longitude": longitude,
        "filters": geospatial_layers,
        "overlay_ids": overlay_ids,
        "basemap_id": basemap_id,
        "aoi": aoi,
        "commute": commute,
        "bbox": bbox,
        "image_width": server_settings.gibs.image_width,
        "image_height": server_settings.gibs.image_height,
        "map_size_m": map_size_m if map_size_m is not None else server_settings.map.default_size_m,
        "map_tiles": resolved_tiles,
    }
    if radius_m is not None:
        payload_data["radius_m"] = radius_m
    if image_crs is not None:
        payload_data["image_crs"] = image_crs
    if image_format is not None:
        payload_data["image_format"] = image_format
    return payload_data


def _resolve_tiles_from_basemap(basemap_id: str | None) -> str | None:
    selected = (basemap_id or "").strip()
    if not selected:
        return None
    try:
        basemaps = GeospatialManifestLoader().load_all().get("basemaps", [])
    except Exception:
        return None
    for entry in basemaps:
        if str(entry.get("id")) != selected:
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        tile_url = metadata.get("tile_url")
        if isinstance(tile_url, str) and tile_url.strip():
            if selected == "osm_default":
                return "OpenStreetMap"
            return tile_url
    if selected == "osm_default":
        return "OpenStreetMap"
    return None


def build_search_response(
    *, search_payload: dict[str, Any], map_session: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status_message": MAP_SEARCH_STATUS_MESSAGE,
        "payload": search_payload,
        "map_session": map_session,
        "compliance_warnings": map_session.get("compliance_warnings", []),
    }
