from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.domain.geospatial.providers import ProviderResponse
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.capability_execution import (
    CapabilityExecutionService,
    ToolExecutionContext,
)
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.geospatial.providers.base import (
    ProviderInvalidQueryError,
    ProviderTimeoutError,
)


###############################################################################
class FakeCapabilityRegistry:

    # -------------------------------------------------------------------------
    def __init__(self, manifest: dict[str, object] | None) -> None:
        self.manifest = manifest

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict[str, object] | None:
        return self.manifest if capability_id == "places:hospitals" else None


###############################################################################
class FakeRuntimeRegistry:

    # -------------------------------------------------------------------------
    def __init__(self, *, enabled: bool = True, available: bool = True) -> None:
        self.enabled = enabled
        self.available = available

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return self.enabled

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return self.available


###############################################################################
class FakeProviderRegistry:

    # -------------------------------------------------------------------------
    def __init__(self, response: ProviderResponse | Exception) -> None:
        self.response = response
        self.requests: list[tuple[str, object]] = []

    # -------------------------------------------------------------------------
    async def fetch(self, provider_id: str, request: object) -> ProviderResponse:
        self.requests.append((provider_id, request))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


###############################################################################
class FakeEvidenceRepository:

    # -------------------------------------------------------------------------
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.error = error

    # -------------------------------------------------------------------------
    def create(self, **kwargs: object) -> SimpleNamespace:
        if self.error is not None:
            raise self.error
        self.calls.append(kwargs)
        return SimpleNamespace(evidence_id="evidence:provider-1")


###############################################################################
def _service(
    provider: FakeProviderRegistry,
    evidence: FakeEvidenceRepository | None = None,
    runtime: FakeRuntimeRegistry | None = None,
) -> CapabilityExecutionService:
    return CapabilityExecutionService(
        capability_registry=FakeCapabilityRegistry(
            {"id": "places:hospitals", "provider": "overpass"}
        ),
        runtime_registry=runtime or FakeRuntimeRegistry(),
        provider_registry=provider,  # type: ignore[arg-type]
        evidence_repository=evidence,
    )


###############################################################################
@pytest.mark.asyncio
async def test_execute_capability_persists_full_payload_and_returns_bounded_summary() -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="overpass",
        payload={"type": "FeatureCollection", "features": [{"id": "a"}]},
        result_type="features",
    )
    evidence = FakeEvidenceRepository()
    provider = FakeProviderRegistry(response)
    service = _service(provider, evidence)

    result = await service.execute_capability(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            operation="within_distance",
            location_ref="location:zurich-hb",
            radius_m=5000,
            filters={"category": "hospital"},
        ),
        ToolExecutionContext(
            conversation_id="conversation-1",
            run_id="run-1",
            call_id="call-1",
        ),
    )

    assert result.status == "success"
    assert result.call_id == "call-1"
    assert result.evidence_refs == ["evidence:provider-1"]
    assert result.data == {
        "capability_id": "places:hospitals",
        "provider_id": "overpass",
        "result_status": "ok",
        "result_type": "features",
        "feature_count": 1,
        "stale": False,
    }
    assert evidence.calls[0]["payload"] == response.payload
    request = provider.requests[0][1]
    assert request.params["filters"] == {"category": "hospital"}  # type: ignore[attr-defined]
    assert request.params["radius_m"] == 5000  # type: ignore[attr-defined]


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_status", "partial", "expected_status"),
    [("valid_empty", False, "valid_empty"), ("stale", False, "partial")],
)
async def test_provider_statuses_are_normalized(
    response_status: str,
    partial: bool,
    expected_status: str,
) -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="overpass",
        payload={},
        result_status=response_status,  # type: ignore[arg-type]
        partial=partial,
    )
    result = await _service(FakeProviderRegistry(response)).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == expected_status


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "error_type", "recovery"),
    [
        (ProviderTimeoutError("upstream"), "timeout", "replan"),
        (
            ProviderInvalidQueryError("invalid"),
            "semantic_validation",
            "correct_arguments",
        ),
    ],
)
async def test_provider_failures_remain_typed(
    error: Exception,
    error_type: str,
    recovery: str,
) -> None:
    result = await _service(FakeProviderRegistry(error)).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.error_type == error_type
    assert result.error.recovery == recovery


###############################################################################
@pytest.mark.asyncio
async def test_disabled_capability_is_rejected_before_provider_execution() -> None:
    provider = FakeProviderRegistry(
        ProviderResponse(
            capability_id="places:hospitals",
            provider_id="overpass",
            payload={},
        )
    )
    result = await _service(
        provider,
        runtime=FakeRuntimeRegistry(enabled=False),
    ).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.error is not None
    assert result.error.code == "capability_disabled"
    assert provider.requests == []


###############################################################################
@pytest.mark.asyncio
async def test_evidence_persistence_failure_is_a_typed_result() -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="overpass",
        payload={"features": []},
        result_type="features",
    )
    result = await _service(
        FakeProviderRegistry(response),
        FakeEvidenceRepository(error=ValueError("storage failure")),
    ).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.error_type == "provider_malformed_response"


###############################################################################
@pytest.mark.asyncio
async def test_resolved_location_is_forwarded_as_provider_coordinates() -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="overpass",
        payload={"features": []},
    )
    provider = FakeProviderRegistry(response)
    await _service(provider).execute_capability(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            location_ref="zurich",
        ),
        ToolExecutionContext(conversation_id="conversation-1"),
        location=ResolvedLocation(
            label="Zurich",
            latitude=47.3769,
            longitude=8.5417,
        ),
    )

    request = provider.requests[0][1]
    assert request.params["latitude"] == 47.3769  # type: ignore[attr-defined]
    assert request.params["longitude"] == 8.5417  # type: ignore[attr-defined]
