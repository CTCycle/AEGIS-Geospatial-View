from __future__ import annotations

from types import SimpleNamespace

from AEGIS.server.api.search import MapRenderingService


class _ToolkitStub:
    def harmonize_bbox_crs(self, bbox, *, source_crs, target_crs):  # noqa: ANN001
        return bbox


class _MapServiceStub:
    def compute_bbox_from_center(self, lon: float, lat: float, size: float):  # noqa: ANN001
        return [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1]


def _build_service() -> MapRenderingService:
    service = MapRenderingService.__new__(MapRenderingService)
    service.toolkit = _ToolkitStub()
    service.map_service = _MapServiceStub()
    return service


def test_derive_map_bbox_prefers_explicit_bbox() -> None:
    service = _build_service()
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
