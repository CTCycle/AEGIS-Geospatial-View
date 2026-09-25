from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from server.domain.agent.tool_result import (
    ModelObservation,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.geospatial.providers import ProviderResponse
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.capability_execution import (
    CapabilityExecutionService,
    ToolExecutionContext,
    _response_summary,
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
    manifest: dict[str, object] | None = None,
) -> CapabilityExecutionService:
    return CapabilityExecutionService(
        capability_registry=FakeCapabilityRegistry(
            manifest or {"id": "places:hospitals", "provider": "overpass"}
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
        payload={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "a",
                    "geometry": {"type": "Point", "coordinates": [8.54, 47.37]},
                    "properties": {"name": "Hospital"},
                }
            ],
        },
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
    assert isinstance(result.data, dict)
    assert result.data.items() >= {
        "capability_id": "places:hospitals",
        "provider_id": "overpass",
        "result_status": "ok",
        "result_type": "features",
        "feature_count": 1,
        "map_eligibility": "renderable",
        "stale": False,
        "bbox": [8.54, 47.37, 8.54, 47.37],
    }.items()
    assert result.data["query"] == {
        "operation": "within_distance",
        "location_ref": "location:zurich-hb",
        "resolved_location": None,
        "bbox": None,
        "radius_m": 5000.0,
        "start_time_iso": None,
        "end_time_iso": None,
        "filter_keys": ["category"],
    }
    assert evidence.calls[0]["payload"] == response.payload
    request = provider.requests[0][1]
    assert request.params["filters"] == {"category": "hospital"}  # type: ignore[attr-defined]
    assert request.params["radius_m"] == 5000  # type: ignore[attr-defined]


###############################################################################
def test_feature_summary_exposes_bounded_preview_to_model() -> None:
    features = [
        {
            "id": f"overpass:{index}",
            "name": f"Pharmacy {index}",
            "category": "pharmacy",
            "source": "overpass",
            "latitude": 41.89 + index / 10000,
            "longitude": 12.49,
            "metadata": {"distance_m": index * 100.0, "raw_tags": "omit"},
        }
        for index in range(12)
    ]
    summary = _response_summary(
        ProviderResponse(
            capability_id="overpass_poi_amenities",
            provider_id="overpass",
            payload={"features": features},
            result_type="features",
        )
    )

    observation = ModelObservation.from_tool_result(
        ToolResult(
            call_id="pois-1",
            tool_name="execute_geospatial_capability",
            status="success",
            summary="12 pharmacy features returned.",
            data=summary,
            metadata=ToolExecutionMetadata(duration_ms=0),
        )
    )

    assert summary["feature_count"] == 12
    assert summary["feature_preview_truncated"] is True
    assert isinstance(observation.result, dict)
    preview = observation.result["feature_preview"]
    assert isinstance(preview, list)
    assert len(preview) == 10
    assert preview[0] == {
        "id": "overpass:0",
        "name": "Pharmacy 0",
        "category": "pharmacy",
        "latitude": 41.89,
        "longitude": 12.49,
        "distance_m": 0.0,
    }
    assert preview[-1]["name"] == "Pharmacy 9"
    assert all("raw_tags" not in item for item in preview)

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


###############################################################################
@pytest.mark.asyncio
async def test_manifest_metadata_is_forwarded_to_descriptor_provider() -> None:
    response = ProviderResponse(
        capability_id="esa_worldcover",
        provider_id="esa",
        payload={"renderingMode": "wmts", "serviceUrl": "https://example.test/wmts"},
        result_type="raster",
    )
    provider = FakeProviderRegistry(response)
    service = _service(
        provider,
        manifest={
            "id": "places:hospitals",
            "provider": "esa",
            "metadata": {
                "url": "https://example.test/wmts",
                "layer_id": "WORLDCOVER_2021_MAP",
            },
        },
    )

    await service.execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    request = provider.requests[0][1]
    assert request.params["metadata"] == {  # type: ignore[attr-defined]
        "url": "https://example.test/wmts",
        "layer_id": "WORLDCOVER_2021_MAP",
    }


###############################################################################
def test_weather_summary_exposes_bounded_current_observations() -> None:
    summary = _response_summary(
        ProviderResponse(
            capability_id="get_weather_forecast",
            provider_id="openmeteo",
            payload={
                "kind": "weather_forecast",
                "current": {
                    "temperature_2m": 27.3,
                    "relative_humidity_2m": 62,
                    "wind_speed_10m": 9.5,
                    "secret": "must not be copied",
                },
                "timezone": "Europe/Rome",
            },
        )
    )

    assert summary["observations"] == {
        "temperature_2m": 27.3,
        "relative_humidity_2m": 62,
        "wind_speed_10m": 9.5,
    }
    assert summary["timezone"] == "Europe/Rome"


###############################################################################
@pytest.mark.parametrize(
    ("kind", "rows", "expected_fields"),
    [
        (
            "weather_forecast",
            [
                {
                    "time": (datetime(2026, 5, 11) + timedelta(hours=hour)).strftime(
                        "%Y-%m-%dT%H:%M"
                    ),
                    "temperature_2m": hour,
                    "precipitation": 0.0,
                    "wind_speed_10m": 2.0,
                    "secret": "omit",
                }
                for hour in range(48)
            ],
            {"time", "temperature_2m", "precipitation", "wind_speed_10m"},
        ),
        (
            "air_quality_forecast",
            [
                {
                    "time": (datetime(2026, 5, 11) + timedelta(hours=hour)).strftime(
                        "%Y-%m-%dT%H:%M"
                    ),
                    "pm2_5": hour,
                    "secret": "omit",
                }
                for hour in range(48)
            ],
            {"time", "pm2_5"},
        ),
    ],
)
def test_forecast_summary_exposes_at_most_24_allowlisted_hourly_rows(
    kind: str,
    rows: list[dict[str, object]],
    expected_fields: set[str],
) -> None:
    summary = _response_summary(
        ProviderResponse(
            capability_id="get_weather_forecast",
            provider_id="openmeteo",
            payload={
                "kind": kind,
                "hourlyForecast": rows,
                "timezone": "Europe/Rome",
            },
            fetched_at=datetime(2026, 5, 11, 8, 30, tzinfo=UTC),
        )
    )

    assert summary["forecast_hours"] == 24
    assert summary["forecast_hours_requested"] == 24
    assert summary["forecast_truncated"] is False
    assert summary["forecast_window_status"] == "ok"
    assert len(summary["hourly_forecast"]) == 24
    assert set(summary["hourly_forecast"][0]) == expected_fields
    assert "secret" not in summary["hourly_forecast"][0]
    assert summary["forecast_window_start"] == "2026-05-11T11:00"
    assert summary["forecast_window_end"] == "2026-05-12T10:00"
    assert summary["timezone"] == "Europe/Rome"

    observation = ModelObservation.from_tool_result(
        ToolResult(
            call_id="forecast-1",
            tool_name="execute_geospatial_capability",
            status="success",
            summary="Hourly forecast returned.",
            data=summary,
            metadata=ToolExecutionMetadata(duration_ms=0),
        ),
        max_chars=2048,
    )
    projected = observation.result
    assert isinstance(projected, dict)
    series = projected["hourly_forecast"]
    assert isinstance(series, dict)
    assert len(series["rows"]) == 24
    assert series["fields"][0] == "time"
    assert len(json.dumps(projected, separators=(",", ":"))) <= 2048


###############################################################################
def test_raster_summary_is_renderable_only_with_a_source() -> None:
    renderable = _response_summary(
        ProviderResponse(
            capability_id="esa_worldcover",
            provider_id="esa",
            payload={"renderingMode": "wmts", "serviceUrl": "https://example.test/wmts"},
            result_type="raster",
        )
    )
    unavailable = _response_summary(
        ProviderResponse(
            capability_id="esa_worldcover",
            provider_id="esa",
            payload={"renderingMode": "wmts"},
            result_type="raster",
        )
    )

    assert renderable["map_eligibility"] == "renderable"
    assert unavailable["map_eligibility"] == "unknown"
