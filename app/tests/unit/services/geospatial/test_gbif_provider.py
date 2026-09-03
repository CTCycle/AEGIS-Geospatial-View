from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.gbif import GBIFProvider


###############################################################################
def test_gbif_provider_normalizes_occurrence_provenance() -> None:
    requested_urls: list[str] = []

    async def fetcher(url: str, _headers: dict[str, str] | None = None) -> object:
        requested_urls.append(url)
        return {
            "count": 2,
            "endOfRecords": True,
            "results": [
                {
                    "key": 123,
                    "scientificName": "Lynx lynx (Linnaeus, 1758)",
                    "species": "Lynx lynx",
                    "taxonKey": 2435240,
                    "decimalLatitude": 46.2,
                    "decimalLongitude": 8.8,
                    "eventDate": "2026-08-20T00:00:00",
                    "basisOfRecord": "HUMAN_OBSERVATION",
                    "datasetKey": "dataset-1",
                    "coordinateUncertaintyInMeters": 50.0,
                    "issues": ["COORDINATE_ROUNDED"],
                    "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
                },
                {
                    "key": 124,
                    "scientificName": "Invalid location",
                    "decimalLatitude": None,
                    "decimalLongitude": None,
                },
            ],
        }

    provider = GBIFProvider(fetcher=fetcher)
    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
                params={"limit": 100, "taxonKey": 2435240},
            )
        )
    )

    assert response.result_status == "ok"
    assert response.result_type == "features"
    assert response.payload["totalMatched"] == 2
    features = response.payload["features"]
    assert isinstance(features, list)
    assert len(features) == 1
    feature = features[0]
    assert feature["name"] == "Lynx lynx"
    assert feature["category"] == "species_occurrence"
    assert feature["metadata"]["basisOfRecord"] == "HUMAN_OBSERVATION"
    assert feature["metadata"]["datasetKey"] == "dataset-1"
    assert feature["metadata"]["coordinateUncertaintyInMeters"] == 50.0
    assert feature["metadata"]["issues"] == ["COORDINATE_ROUNDED"]
    assert feature["metadata"]["license"].startswith("http://creativecommons.org/")

    query = parse_qs(urlparse(requested_urls[0]).query)
    assert query["hasCoordinate"] == ["true"]
    assert query["limit"] == ["100"]
    assert query["taxon_key"] == ["2435240"]
    assert query["geometry"][0].startswith("POLYGON((8.0 46.0")
