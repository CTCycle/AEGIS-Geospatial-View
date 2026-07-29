from __future__ import annotations

import json
from asyncio import run

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.tiler import build_vector_tile_manifest

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
def test_mobility_database_search_uses_local_snapshot(tmp_path) -> None:
    catalog = tmp_path / "feeds.csv"
    catalog.write_text(
        "mdb_source_id,provider,name,location.country_code,urls.latest,urls.license\n"
        "mdb-1,Example Transit,Example City,IT,https://agency.example/gtfs.zip,https://agency.example/license\n",
        encoding="utf-8",
    )
    from server.services.geospatial.providers.mobility_database import MobilityDatabaseProvider

    registry = ProviderRegistry(providers=[MobilityDatabaseProvider(catalog_path=catalog)])

    response = run(
        registry.fetch(
            "mobility_database",
            ProviderRequest(capability_id="mobility_database_feeds", params={"query": "Example"}),
        )
    )

    assert response.payload["feedCount"] == 1
    assert response.payload["feeds"][0]["staticFeedUrl"].endswith("gtfs.zip")
    assert response.payload["feeds"][0]["license"].endswith("license")

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
