from __future__ import annotations

import asyncio
from collections.abc import Mapping

from server.domain.geographics import ProviderCredentialValidationResult
from server.services.geospatial.provider_credential_validation_service import (
    ProviderCredentialValidationService,
)
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderError, ProviderRequest, ProviderResponse


class _ValidationProvider:
    provider_id = "geoapify"

    def __init__(self, result: ProviderCredentialValidationResult | None = None) -> None:
        self.result = result

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={},
        )

    async def fetch_features(self, request: ProviderRequest) -> ProviderResponse:
        return await self.fetch(request)

    async def validate_credentials(
        self, credentials: Mapping[str, str]
    ) -> ProviderCredentialValidationResult:
        if self.result is None:
            raise ProviderError("network failed")
        return self.result


def test_provider_credential_validation_missing_key_returns_invalid() -> None:
    service = ProviderCredentialValidationService()

    result = asyncio.run(service.validate("geoapify", {}))

    assert result.valid is False
    assert result.status == "invalid"


def test_provider_credential_validation_no_key_provider_returns_valid() -> None:
    service = ProviderCredentialValidationService()

    result = asyncio.run(service.validate("openmeteo", {}))

    assert result.valid is True
    assert result.status == "valid"


def test_provider_credential_validation_provider_success_returns_valid() -> None:
    registry = ProviderRegistry(
        providers=[
            _ValidationProvider(
                ProviderCredentialValidationResult(
                    provider_id="geoapify",
                    valid=True,
                    status="valid",
                    message="accepted",
                )
            )
        ]
    )
    service = ProviderCredentialValidationService(provider_registry=registry)

    result = asyncio.run(service.validate("geoapify", {"api_key": "secret-key"}))

    assert result.valid is True
    assert "secret-key" not in result.message


def test_provider_credential_validation_provider_failure_returns_invalid() -> None:
    registry = ProviderRegistry(
        providers=[
            _ValidationProvider(
                ProviderCredentialValidationResult(
                    provider_id="geoapify",
                    valid=False,
                    status="invalid",
                    message="rejected",
                )
            )
        ]
    )
    service = ProviderCredentialValidationService(provider_registry=registry)

    result = asyncio.run(service.validate("geoapify", {"api_key": "secret-key"}))

    assert result.valid is False
    assert result.status == "invalid"
    assert "secret-key" not in result.message


def test_provider_credential_validation_provider_error_returns_error() -> None:
    registry = ProviderRegistry(providers=[_ValidationProvider()])
    service = ProviderCredentialValidationService(provider_registry=registry)

    result = asyncio.run(service.validate("geoapify", {"api_key": "secret-key"}))

    assert result.valid is False
    assert result.status == "error"
    assert "secret-key" not in result.message
