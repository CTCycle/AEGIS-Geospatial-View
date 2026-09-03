from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest

from server.services.geospatial.providers.base import (
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.gbif import GBIFProvider


###############################################################################
def _provider_for_payload(
    payload: object,
) -> tuple[GBIFProvider, list[str]]:
    requested_urls: list[str] = []

    async def fetcher(url: str, _headers: dict[str, str] | None = None) -> object:
        requested_urls.append(url)
        return payload

    return GBIFProvider(fetcher=fetcher), requested_urls


###############################################################################
def test_gbif_provider_normalizes_occurrence_provenance() -> None:
    provider, requested_urls = _provider_for_payload(
        {
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
                    "datasetTitle": "Alpine observations",
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
    )
    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
                params={
                    "limit": 100,
                    "taxonKey": 2435240,
                    "basisOfRecord": "HUMAN_OBSERVATION",
                },
            )
        )
    )

    assert response.result_status == "ok"
    assert response.result_type == "features"
    assert response.attribution == ["GBIF.org and contributing datasets"]
    assert response.payload["totalMatched"] == 2
    features = response.payload["features"]
    assert isinstance(features, list)
    assert len(features) == 1
    feature = features[0]
    assert feature["name"] == "Lynx lynx"
    assert feature["category"] == "species_occurrence"
    assert feature["url"] == "https://www.gbif.org/occurrence/123"
    assert feature["occurrenceUrl"] == "https://www.gbif.org/occurrence/123"
    assert feature["datasetUrl"] == "https://www.gbif.org/dataset/dataset-1"
    assert feature["metadata"]["basisOfRecord"] == "HUMAN_OBSERVATION"
    assert feature["metadata"]["datasetKey"] == "dataset-1"
    assert feature["metadata"]["occurrenceUrl"] == feature["occurrenceUrl"]
    assert feature["metadata"]["datasetUrl"] == feature["datasetUrl"]
    assert feature["metadata"]["coordinateUncertaintyInMeters"] == 50.0
    assert feature["metadata"]["issues"] == ["COORDINATE_ROUNDED"]
    assert feature["metadata"]["license"].startswith("http://creativecommons.org/")
    assert response.payload["provenance"] == {
        "citationRequired": True,
        "citationGuidanceUrl": "https://www.gbif.org/citation-guidelines",
        "downloadDoi": None,
    }
    assert response.warnings and "contributing datasets" in response.warnings[0]

    query = parse_qs(urlparse(requested_urls[0]).query)
    assert query["hasCoordinate"] == ["true"]
    assert query["limit"] == ["100"]
    assert query["taxonKey"] == ["2435240"]
    assert query["basisOfRecord"] == ["HUMAN_OBSERVATION"]
    assert query["geometry"][0].startswith("POLYGON((8.0 46.0")


###############################################################################
def test_gbif_provider_requires_bounded_non_antimeridian_extent() -> None:
    provider, _requested_urls = _provider_for_payload({})

    with pytest.raises(ProviderUnavailableError, match="bounded"):
        asyncio.run(
            provider.fetch(
                ProviderRequest(
                    capability_id="gbif_species_occurrences",
                    bbox=None,
                )
            )
        )

    with pytest.raises(ProviderUnavailableError, match="antimeridian"):
        asyncio.run(
            provider.fetch(
                ProviderRequest(
                    capability_id="gbif_species_occurrences",
                    bbox=(179.0, -10.0, -179.0, 10.0),
                )
            )
        )


###############################################################################
def test_gbif_provider_clamps_interactive_limit_to_300() -> None:
    provider, requested_urls = _provider_for_payload(
        {"count": 0, "endOfRecords": True, "results": []}
    )

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
                params={"limit": 999},
            )
        )
    )

    assert response.result_status == "valid_empty"
    assert response.payload["sampleLimit"] == 300
    assert parse_qs(urlparse(requested_urls[0]).query)["limit"] == ["300"]


###############################################################################
def test_gbif_provider_marks_sampled_results() -> None:
    provider, _requested_urls = _provider_for_payload(
        {
            "count": 301,
            "endOfRecords": False,
            "results": [
                {
                    "key": 1,
                    "decimalLatitude": 46.2,
                    "decimalLongitude": 8.8,
                },
                {
                    "key": 2,
                    "decimalLatitude": 46.3,
                    "decimalLongitude": 8.9,
                },
            ],
        }
    )

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
                params={"limit": 2},
            )
        )
    )

    assert response.payload["sampled"] is True
    assert response.payload["totalMatched"] == 301
    assert response.payload["sampleLimit"] == 2
    assert any("limited to 2" in warning for warning in response.warnings)


###############################################################################
def test_gbif_provider_filters_invalid_coordinates_and_supports_empty_results() -> None:
    provider, _requested_urls = _provider_for_payload(
        {
            "count": 5,
            "endOfRecords": True,
            "results": [
                {"key": 1, "decimalLatitude": 46.0, "decimalLongitude": 8.0},
                {"key": 2, "decimalLatitude": 91.0, "decimalLongitude": 8.0},
                {"key": 3, "decimalLatitude": 46.0, "decimalLongitude": 181.0},
                {"key": 4, "decimalLatitude": "not-a-number", "decimalLongitude": 8.0},
                {"key": 5, "decimalLatitude": float("nan"), "decimalLongitude": 8.0},
            ],
        }
    )

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 45.0, 9.0, 47.0),
            )
        )
    )

    assert response.result_status == "ok"
    assert [feature["id"] for feature in response.payload["features"]] == ["1"]

    empty_provider, _requested_urls = _provider_for_payload(
        {"count": 0, "endOfRecords": True, "results": []}
    )
    empty_response = asyncio.run(
        empty_provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 45.0, 9.0, 47.0),
            )
        )
    )
    assert empty_response.result_status == "valid_empty"
    assert empty_response.payload["features"] == []


###############################################################################
@pytest.mark.parametrize("payload", [[], {}, {"results": {}}])
def test_gbif_provider_rejects_malformed_payloads(payload: object) -> None:
    provider, _requested_urls = _provider_for_payload(payload)

    with pytest.raises(ProviderMalformedPayloadError):
        asyncio.run(
            provider.fetch(
                ProviderRequest(
                    capability_id="gbif_species_occurrences",
                    bbox=(8.0, 45.0, 9.0, 47.0),
                )
            )
        )
