from __future__ import annotations

import asyncio

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import (
    FeatureRequest,
    ProviderRequest,
    ProviderResponse,
    ProviderResult,
    provider_cache_key,
    safe_request_params,
)


class _FeatureOnlyProvider:
    provider_id = "feature_only"

    async def fetch_features(self, request: FeatureRequest) -> ProviderResult:
        return ProviderResult(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"api_key": "should-not-leak", "value": 1},
            attribution=["Example Attribution"],
        )

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        raise AssertionError("fetch_features should be preferred")


def test_provider_registry_prefers_canonical_fetch_features_contract() -> None:
    registry = ProviderRegistry(providers=[_FeatureOnlyProvider()])

    response = asyncio.run(
        registry.fetch("feature_only", FeatureRequest(capability_id="sample"))
    )

    assert response.payload == {"api_key": "<redacted>", "value": 1}
    assert response.attribution == ["Example Attribution"]


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


def test_safe_request_params_redacts_credentials() -> None:
    params = safe_request_params(
        {"token": "abc", "authorization": "Bearer abc", "category": "parks"}
    )

    assert params == {
        "authorization": "<redacted>",
        "category": "parks",
        "token": "<redacted>",
    }
