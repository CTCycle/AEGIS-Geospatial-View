from __future__ import annotations

from datetime import date

from server.domain.catalog import GeospatialLayerReferenceEntry
from server.services.geospatial.gibs import (
    GIBSRequestError,
    GIBSService,
)
from server.domain.gibs import LayerMetadata
from server.services.geospatial.layers import LayerProviderService
from server.services.geospatial.maps import MapService, MapValidationError


def test_layer_provider_maps_active_fires_to_supported_provider_layer() -> None:
    service = LayerProviderService(
        layer_catalog=(
            GeospatialLayerReferenceEntry(
                layer_id="MODIS_Combined_Thermal_Anomalies_Fire",
                display_name="Active Fires (MODIS, Daily)",
                group="gibs_nrt",
                provider="gibs",
                aliases=("active fires", "fire", "fires"),
                keywords=("active fires", "fire", "fires"),
            ),
        )
    )

    entry = service.resolve("MODIS_Combined_Thermal_Anomalies_Fire")

    assert entry.name == "MODIS_Combined_Thermal_Anomalies_Fire"
    assert entry.provider_name == "MODIS_Combined_Thermal_Anomalies_All"


def test_map_service_rejects_removed_jawg_map() -> None:
    service = MapService()

    try:
        service.resolve_base_tiles("Jawg.Dark")
    except MapValidationError as exc:
        assert "not available" in str(exc)
    else:  # pragma: no cover - defensive failure branch
        raise AssertionError("Expected removed Jawg map to be rejected")


def test_map_service_rejects_removed_thunderforest_map() -> None:
    service = MapService()

    try:
        service.resolve_base_tiles("Thunderforest.Transport")
    except MapValidationError as exc:
        assert "not available" in str(exc)
    else:  # pragma: no cover - defensive failure branch
        raise AssertionError("Expected removed Thunderforest map to be rejected")


def test_gibs_service_retries_previous_date_for_known_layer(monkeypatch) -> None:
    class _ReferenceRepository:
        def load_gibs_layer_native_resolution_map(self) -> dict[str, float]:
            return {}

        def load_gibs_layer_date_fallback_days_map(self) -> dict[str, int]:
            return {"MODIS_Combined_Thermal_Anomalies_All": 3}

    service = GIBSService(reference_repository=_ReferenceRepository())

    monkeypatch.setattr(
        service,
        "resolve_capabilities_for_layer",
        lambda **_: (object(), "EPSG:3857"),
    )
    monkeypatch.setattr(
        service,
        "extract_layer",
        lambda layer, _capabilities: LayerMetadata(
            name=layer,
            supported_crs=frozenset({"EPSG:3857"}),
            formats=frozenset({"image/png"}),
            time_extent=None,
        ),
    )
    monkeypatch.setattr(service, "resolve_layer_crs", lambda *_: "EPSG:3857")
    monkeypatch.setattr(
        service,
        "compute_meters_per_pixel",
        lambda *_: {"x": 1.0, "y": 1.0},
    )

    requested_dates: list[str] = []

    def fake_execute_request(url: str, timeout_s: int) -> tuple[bytes, str, str]:
        del timeout_s
        requested_dates.append(url.rsplit("TIME=", 1)[-1])
        if requested_dates[-1] == "2026-04-01":
            raise GIBSRequestError(
                "msShapefileOpen(): The requested shapefile cannot be found."
            )
        return (b"png-bytes" * 256, "image/png", url)

    monkeypatch.setattr(service, "execute_request", fake_execute_request)

    response = service.fetch_image(
        lon=None,
        lat=None,
        bbox=[-8577833.0, 4707061.0, -8567833.0, 4717061.0],
        radius_m=2500.0,
        date=date(2026, 4, 1).isoformat(),
        layer="MODIS_Combined_Thermal_Anomalies_All",
        width=512,
        height=512,
        crs="EPSG:3857",
        format="image/png",
        skip_bbox_expansion=True,
    )

    assert requested_dates[:2] == ["2026-04-01", "2026-03-31"]
    assert response["date"] == "2026-03-31"
