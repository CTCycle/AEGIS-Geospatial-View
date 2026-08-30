from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import (
    FeatureRequest,
    ProviderRequest,
    ProviderResponse,
    ProviderResult,
    provider_cache_key,
    safe_request_params,
)
from server.services.geospatial.providers.nominatim import NominatimProvider
from server.services.geospatial.providers.mobility_database import (
    MobilityDatabaseProvider,
)


###############################################################################
class _FeatureOnlyProvider:
    provider_id = "feature_only"

    # -------------------------------------------------------------------------
    async def fetch_features(self, request: FeatureRequest) -> ProviderResult:
        return ProviderResult(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"api_key": "should-not-leak", "value": 1},
            attribution=["Example Attribution"],
        )

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        raise AssertionError("fetch_features should be preferred")


###############################################################################
def test_provider_registry_prefers_canonical_fetch_features_contract() -> None:
    registry = ProviderRegistry(providers=[_FeatureOnlyProvider()])

    response = run_async_in_thread(
        registry.fetch("feature_only", FeatureRequest(capability_id="sample"))
    )

    assert response.payload == {"api_key": "<redacted>", "value": 1}
    assert response.attribution == ["Example Attribution"]


###############################################################################
def test_provider_cache_key_uses_safe_stable_request_parts() -> None:
    request = FeatureRequest(
        capability_id="layer",
        bbox=(-1.0, 2.0, 3.0, 4.0),
        zoom=8,
        params={"category": "hospital", "api_key": "secret"},
    )

    key_a = provider_cache_key("Provider", request)
    key_b = provider_cache_key("provider", request)

    assert key_a == key_b
    assert "secret" not in key_a
    assert key_a.startswith("provider:layer:")


###############################################################################
def test_safe_request_params_redacts_credentials() -> None:
    params = safe_request_params(
        {"token": "abc", "authorization": "Bearer abc", "category": "parks"}
    )

    assert params == {
        "authorization": "<redacted>",
        "category": "parks",
        "token": "<redacted>",
    }


###############################################################################
def test_nominatim_provider_geocodes_live_contract_payload() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None = None):
        assert "q=Rome" in url
        assert headers and "User-Agent" in headers
        return [
            {
                "place_id": 1,
                "display_name": "Rome, Roma Capitale, Lazio, Italy",
                "lat": "41.8933",
                "lon": "12.4829",
                "type": "city",
            }
        ]

    response = run_async_in_thread(
        NominatimProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="location_to_coordinates",
                params={"query": "Rome"},
            )
        )
    )

    assert response.payload["resultCount"] == 1
    assert response.payload["results"][0]["latitude"] == 41.8933


###############################################################################
def test_mobility_database_provider_searches_local_snapshot(tmp_path) -> None:
    catalog = tmp_path / "feeds.csv"
    catalog.write_text(
        "mdb_source_id,provider,name,urls.latest,urls.license,urls.authentication_type\n"
        "f-test,Example Transit,Example Transit,https://agency.example/gtfs.zip,https://agency.example/license,1\n",
        encoding="utf-8",
    )
    response = run_async_in_thread(
        MobilityDatabaseProvider(catalog_path=catalog).fetch(
            ProviderRequest(
                capability_id="mobility_database_feeds", params={"query": "Example"}
            )
        )
    )

    assert response.payload["feedCount"] == 1
    assert response.payload["feeds"][0]["staticFeedUrl"].endswith("gtfs.zip")
    assert response.payload["feeds"][0]["authentication"]["required"] is True
