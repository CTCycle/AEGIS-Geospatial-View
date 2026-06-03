from __future__ import annotations

from server.domain.catalog import GeospatialLayerReferenceEntry
from server.services.geospatial.layers import (
    LayerProviderService,
    build_geospatial_layer_catalog,
)


def test_geospatial_layer_catalog_comes_from_reference_entries() -> None:
    service = LayerProviderService(
        layer_catalog=(
            GeospatialLayerReferenceEntry(
                layer_id="MODIS_Combined_Thermal_Anomalies_Fire",
                display_name="Active Fires (MODIS, Daily)",
                group="gibs_nrt",
                provider="gibs",
                aliases=("fire", "fires"),
                keywords=("fire", "fires"),
            ),
        )
    )

    entry = service.resolve("fires")

    assert entry.name == "MODIS_Combined_Thermal_Anomalies_Fire"
    assert entry.label == "Active Fires (MODIS, Daily)"
    assert entry.provider_name == "MODIS_Combined_Thermal_Anomalies_All"


def test_geospatial_layer_service_without_catalog_has_no_entries() -> None:
    service = LayerProviderService()

    assert service.list_options() == {}


def test_build_geospatial_layer_catalog_uses_reference_repository(monkeypatch) -> None:
    expected_catalog = (
        GeospatialLayerReferenceEntry(
            layer_id="fire",
            display_name="Fire",
            group="gibs_nrt",
            provider="gibs",
            aliases=("fires",),
            keywords=("fire",),
        ),
    )

    class RepositoryStub:
        def __init__(self, database) -> None:
            self.database = database

        def load_geospatial_layer_catalog(self):  # noqa: ANN201
            return expected_catalog

    monkeypatch.setattr(
        "server.services.geospatial.layers.ReferenceCatalogRepository",
        RepositoryStub,
    )

    service = build_geospatial_layer_catalog(object())

    assert isinstance(service, LayerProviderService)
    assert service.resolve("fires").name == "fire"
