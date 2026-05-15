from __future__ import annotations

from types import SimpleNamespace

from server.services.geospatial.rendering import MapRenderingService


###############################################################################
class _ToolkitStub:
    def harmonize_bbox_crs(self, bbox, *, source_crs, target_crs):  # noqa: ANN001
        return bbox

    def normalize_layers(self, layers):  # noqa: ANN001
        return list(layers or [])

    def extract_coordinate_pair(self, payload, data):  # noqa: ANN001
        lat = data.get("latitude")
        lon = data.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return (float(lon), float(lat))
        return None


###############################################################################
class _MapServiceStub:
    def compute_bbox_from_center(self, lon: float, lat: float, size: float):  # noqa: ANN001
        return [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1]


###############################################################################
class _RendererStub:
    async def build_satellite_payload(  # noqa: ANN001
        self, payload, search_payload, basemap=None
    ):
        _ = basemap
        return {"bbox": search_payload.get("bbox") or [12.4, 41.8, 12.6, 42.0]}


###############################################################################
class _CatalogStub:
    def resolve_overlays(self, overlay_ids):  # noqa: ANN001
        return []

    def resolve_basemap(self, basemap_id):  # noqa: ANN001
        return {"id": basemap_id or "osm_default"}

    async def fetch_insights(self, latitude, longitude, overlay_ids, radius_m):  # noqa: ANN001
        return {}

    async def fetch_overlay_runtime(self, latitude, longitude, overlay_ids, radius_m):  # noqa: ANN001
        _ = latitude, longitude, radius_m
        return {
            str(overlay_id): {"availability": "available"} for overlay_id in overlay_ids
        }

    def resolve_compliance_warnings(self, basemap, overlays):  # noqa: ANN001
        return []


###############################################################################
class _ElevationStub:
    async def get_elevation(self, lat, lon):  # noqa: ANN001
        return None


###############################################################################
def _build_renderer_service() -> MapRenderingService:
    service = MapRenderingService.__new__(MapRenderingService)
    service.toolkit = _ToolkitStub()
    service.map_service = _MapServiceStub()
    return service


###############################################################################
def test_derive_map_bbox_prefers_explicit_bbox() -> None:
    service = _build_renderer_service()
    payload = SimpleNamespace(
        bbox=[1.0, 2.0, 3.0, 4.0],
        image_crs="EPSG:4326",
        aoi=None,
        map_size_m=2500.0,
    )
    result = service._derive_map_bbox(  # type: ignore[attr-defined]
        bbox_candidate=[0.0, 0.0, 1.0, 1.0],
        bbox_source_crs="EPSG:4326",
        coordinates=(12.5, 41.9),
        payload=payload,
    )
    assert result == [1.0, 2.0, 3.0, 4.0]

