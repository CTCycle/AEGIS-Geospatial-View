from __future__ import annotations

import asyncio
from types import SimpleNamespace
from tests.conftest import run_async_in_thread

from server.services.geospatial.provider_registry import (
    ProviderExecutionPolicy,
    ProviderNotRegisteredError,
    ProviderRegistry,
)
from server.services.geospatial.credential_resolver import GeospatialCredentialResolver
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderCircuitOpenError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

###############################################################################
class _Provider:
    provider_id = "example"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"ok": True},
        )

###############################################################################
class _TimeoutProvider:
    provider_id = "slow"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        await asyncio.sleep(1.0)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"ok": True},
        )

###############################################################################
class _FlakyProvider:
    provider_id = "flaky"

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = 0

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        if self.calls == 1:
            raise ProviderUnavailableError("temporary outage")
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"attempts": self.calls},
        )

###############################################################################
class _AuthProvider:
    provider_id = "auth"

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = 0

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        raise ProviderAuthError("missing key")

###############################################################################
class _SavedCredentialRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.mark_used_calls: list[tuple[str, str]] = []

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        if provider == "tomtom" and label == "api_key":
            return SimpleNamespace(encrypted_value="encrypted-tomtom-key")
        return None

    # -------------------------------------------------------------------------
    def mark_used(self, *, provider: str, label: str) -> None:
        self.mark_used_calls.append((provider, label))

###############################################################################
class _CredentialDecryptor:

    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:
        assert encrypted_value == "encrypted-tomtom-key"
        return "database-only-tomtom-key"

###############################################################################
def test_provider_registry_registers_and_fetches_provider() -> None:
    registry = ProviderRegistry(providers=[_Provider()])

    response = run_async_in_thread(
        registry.fetch("example", ProviderRequest(capability_id="capability"))
    )

    assert registry.list_provider_ids() == ["example"]
    assert response.payload == {"ok": True}

###############################################################################
def test_provider_registry_errors_for_missing_provider() -> None:
    registry = ProviderRegistry()

    try:
        registry.get("missing")
    except ProviderNotRegisteredError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Missing provider unexpectedly resolved.")

###############################################################################
def test_provider_registry_builds_manifest_backed_providers() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    assert "gibs" in registry.list_provider_ids()
    assert "rainviewer" in registry.list_provider_ids()
    assert "fallback" not in registry.list_provider_ids()
    assert "osm" not in registry.list_provider_ids()
    assert "gibs" in registry.list_provider_ids()

###############################################################################
def test_provider_registry_passes_database_only_credentials_to_provider() -> None:
    repository = _SavedCredentialRepository()
    resolver = GeospatialCredentialResolver(
        credentials_repo=repository,  # type: ignore[arg-type]
        crypto_service=_CredentialDecryptor(),
    )
    registry = ProviderRegistry(credential_resolver=resolver)

    registry.build_from_manifests()

    provider = registry.get("tomtom")
    assert getattr(provider, "api_key") == "database-only-tomtom-key"
    assert repository.mark_used_calls == [("tomtom", "api_key")]

###############################################################################
def test_provider_registry_skips_basemap_and_metadata_only_manifests() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    assert "osm_tiles" not in registry.list_provider_ids()

###############################################################################
def test_provider_registry_raises_for_unknown_fetchable_provider() -> None:

    ###############################################################################
    class _Loader:

        # -------------------------------------------------------------------------
        def load_all(self) -> dict[str, list[dict[str, object]]]:
            return {
                "providers": [],
                "basemaps": [],
                "overlays": [
                    {
                        "id": "custom_overlay",
                        "provider": "unknown_provider",
                        "capabilityKind": "raster-overlay",
                    }
                ],
                "cameras": [],
                "transit": [],
                "tools": [],
                "runtime_profiles": [],
            }

    registry = ProviderRegistry(manifest_loader=_Loader())  # type: ignore[arg-type]

    try:
        registry.build_from_manifests()
    except ProviderNotRegisteredError as exc:
        assert "unknown_provider" in str(exc)
    else:
        raise AssertionError("Unknown fetchable provider unexpectedly registered.")

###############################################################################
def test_provider_registry_times_out_slow_provider() -> None:
    registry = ProviderRegistry(
        providers=[_TimeoutProvider()],
        execution_policy=ProviderExecutionPolicy(timeout_seconds=0.01),
    )

    try:
        run_async_in_thread(registry.fetch("slow", ProviderRequest(capability_id="slow_layer")))
    except ProviderTimeoutError as exc:
        assert "slow" in str(exc)
    else:
        raise AssertionError("Slow provider unexpectedly succeeded.")

###############################################################################
def test_provider_registry_retries_transient_provider_failure() -> None:
    provider = _FlakyProvider()
    registry = ProviderRegistry(
        providers=[provider],
        execution_policy=ProviderExecutionPolicy(max_attempts=2),
    )

    response = run_async_in_thread(
        registry.fetch("flaky", ProviderRequest(capability_id="flaky_layer"))
    )

    assert response.payload == {"attempts": 2}

###############################################################################
def test_provider_registry_does_not_retry_auth_errors() -> None:
    provider = _AuthProvider()
    registry = ProviderRegistry(
        providers=[provider],
        execution_policy=ProviderExecutionPolicy(max_attempts=3),
    )

    try:
        run_async_in_thread(registry.fetch("auth", ProviderRequest(capability_id="secure")))
    except ProviderAuthError:
        pass
    else:
        raise AssertionError("Auth provider unexpectedly succeeded.")
    assert provider.calls == 1

###############################################################################
def test_provider_registry_opens_circuit_after_repeated_failures() -> None:
    registry = ProviderRegistry(
        providers=[_TimeoutProvider()],
        execution_policy=ProviderExecutionPolicy(
            timeout_seconds=0.01,
            circuit_breaker_failures=1,
        ),
    )

    try:
        run_async_in_thread(registry.fetch("slow", ProviderRequest(capability_id="slow_layer")))
    except ProviderTimeoutError:
        pass
    else:
        raise AssertionError("Slow provider unexpectedly succeeded.")

    try:
        run_async_in_thread(registry.fetch("slow", ProviderRequest(capability_id="slow_layer")))
    except ProviderCircuitOpenError:
        pass
    else:
        raise AssertionError("Open circuit did not reject the provider.")
