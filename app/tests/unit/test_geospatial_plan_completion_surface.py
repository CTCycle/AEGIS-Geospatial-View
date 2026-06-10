from __future__ import annotations

import json
from asyncio import run

import pytest

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest
from server.services.geospatial.search_index import (
    IndexedFeature,
    build_feature_search_index,
    query_search_index,
)
from server.services.geospatial.tiler import build_vector_tile_manifest


###############################################################################
def test_plan_named_provider_adapters_are_bound() -> None:
    registry = ProviderRegistry()
    registry.build_from_manifests()

    for provider_id in (
        "local_open_data",
        "natural_earth",
        "openaddresses",
        "overture",
        "transitland",
    ):
        assert registry.get(provider_id).provider_id == provider_id


###############################################################################
def test_ingestion_only_providers_return_graceful_state() -> None:
    registry = ProviderRegistry()
    registry.build_from_manifests()

    response = run(
        registry.fetch(
            "natural_earth",
            ProviderRequest(capability_id="natural_earth_admin_boundaries"),
        )
    )

    assert response.payload["status"] == "source-ready"
    assert response.payload["downloadUrl"].startswith("https://")


###############################################################################
def test_transitland_requires_configured_key() -> None:
    registry = ProviderRegistry()
    registry.build_from_manifests()

    with pytest.raises(ProviderAuthError):
        run(
            registry.fetch(
                "transitland",
                ProviderRequest(capability_id="transitland_feeds"),
            )
        )


###############################################################################
def test_search_index_queries_feature_metadata() -> None:
    index = build_feature_search_index(
        [
            IndexedFeature(
                id="1",
                label="Central Hospital",
                category="hospitals",
                source="overpass",
            ),
            IndexedFeature(id="2", label="River Park", category="parks", source="osm"),
        ]
    )

    matches = query_search_index(index, "hospital nearby")

    assert [item.id for item in matches] == ["1"]


###############################################################################
def test_vector_tile_manifest_records_feature_count(tmp_path) -> None:
    geojson = tmp_path / "features.geojson"
    geojson.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "A"},
                        "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_vector_tile_manifest(
        capability_id="sample",
        normalized_geojson=geojson,
        tile_dir=tmp_path / "tiles",
    )

    assert result.feature_count == 1
    assert json.loads((tmp_path / "tiles" / "tile_manifest.json").read_text())[
        "featureCount"
    ] == 1
