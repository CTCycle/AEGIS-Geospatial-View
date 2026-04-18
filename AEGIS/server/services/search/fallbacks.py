from __future__ import annotations

from typing import Any

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService


def build_preview_map_session(
    *,
    catalog_service: GeospatialCatalogService,
    location: dict[str, Any],
    reason: str,
) -> dict[str, Any] | None:
    bbox = location.get("bbox") if isinstance(location.get("bbox"), list) else None
    coordinates = (
        location.get("coordinates")
        if isinstance(location.get("coordinates"), dict)
        else {}
    )
    lat = coordinates.get("latitude")
    lon = coordinates.get("longitude")
    if bbox is None and (lat is None or lon is None):
        return None
    basemap = catalog_service.resolve_basemap("osm_default")
    center = {"latitude": lat, "longitude": lon}
    if bbox and (lat is None or lon is None):
        center = {
            "latitude": (bbox[1] + bbox[3]) / 2.0,
            "longitude": (bbox[0] + bbox[2]) / 2.0,
        }
    return {
        "center": center,
        "bounds": bbox,
        "basemap": basemap,
        "overlays": [],
        "insights": {},
        "compliance_warnings": [],
        "preview_reason": reason,
    }
