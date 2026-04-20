from __future__ import annotations

from typing import Any

from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.common.constants import MAP_SEARCH_STATUS_MESSAGE


def build_request_context(payload: LocationSearchRequest) -> dict[str, Any]:
    return {
        "user": None,
        "country": payload.country,
        "city": payload.city,
        "address": payload.address,
        "longitude": payload.longitude,
        "latitude": payload.latitude,
        "geospatial_layers": list(payload.filters),
        "overlay_ids": list(payload.overlay_ids),
        "basemap_id": payload.basemap_id,
        "map_tiles": payload.map_tiles,
    }


def build_location_search_payload_data(
    payload: LocationSearchRequest,
) -> dict[str, Any]:
    resolved_tiles = (
        _resolve_tiles_from_basemap(payload.basemap_id) or payload.map_tiles
    )
    payload_data = payload.model_dump(mode="python")
    payload_data["map_tiles"] = resolved_tiles
    payload_data["image_width"] = payload.image_width
    payload_data["image_height"] = payload.image_height
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
        metadata = (
            entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        )
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
