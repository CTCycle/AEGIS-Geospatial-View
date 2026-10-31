from __future__ import annotations
import json
import pytest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from server.domain.agent.tool_result import ModelObservation, ToolExecutionMetadata, ToolResult
from server.domain.geospatial.providers import ProviderResponse
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.capability_execution import CapabilityExecutionService, ToolExecutionContext, _response_summary
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.geospatial.providers.base import ProviderInvalidQueryError, ProviderTimeoutError
from typing import Any, cast
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentRunState, CapabilityRoute
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.agent.capability_router import CapabilityRouter, build_location_map_fallback_route
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

# --- test_capability_execution.py ---




###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("coordinates, expected", [([8.5, 47.3], True), ([100, 0], False), ([8.5], False)])
async def test_provider_geometry_is_checked_against_requested_bbox(coordinates, expected) -> None:
    response = ProviderResponse(capability_id="places:hospitals", provider_id="overpass",
        result_type="features", payload={"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": coordinates}}]})
    result = await _service(FakeProviderRegistry(response)).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals", bbox=[8, 47, 9, 48]),
        ToolExecutionContext(conversation_id="conversation-1"))
    assert result.metadata.coverage["spatial_scope_satisfied"] is expected

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_overrides",
    [
        {"bbox": [8, 47, 9, 48]},
        {"location_ref": "new-orleans"},
    ],
)
async def test_raster_result_satisfies_spatial_scope_for_bounded_request(
    input_overrides: dict[str, object],
) -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="fema",
        payload={"renderingMode": "raster-tile", "tileUrl": "https://example.test/export"},
        result_type="raster",
    )
    provider = FakeProviderRegistry(response)

    result = await _service(provider).execute_capability(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            **input_overrides,
        ),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert result.metadata.coverage["spatial_scope_satisfied"] is True

###############################################################################
@pytest.mark.asyncio
async def test_vector_result_over_resolved_location_satisfies_spatial_and_temporal_scope() -> None:
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
    result = await _service(FakeProviderRegistry(response)).execute_capability(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            location_ref="location:zurich-hb",
            radius_m=5000,
            temporal_mode="current",
        ),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert result.metadata.coverage["spatial_scope_satisfied"] is True
    assert result.metadata.coverage["temporal_scope_satisfied"] is True

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("feature", "expected"),
    [
        (
            {
                "id": "a",
                "name": "Event",
                "latitude": 35.6,
                "longitude": 140.7,
                "metadata": {"magnitude": 4.2},
            },
            True,
        ),
        (
            {
                "id": "b",
                "name": "Event",
                "latitude": -70.0,
                "longitude": 0.0,
                "metadata": {"magnitude": 4.2},
            },
            False,
        ),
    ],
)
async def test_normalized_point_feature_is_checked_against_requested_bbox(
    feature: dict[str, object], expected: bool
) -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="usgs",
        payload={"renderingMode": "clustered-points", "features": [feature]},
        result_type="features",
    )
    result = await _service(FakeProviderRegistry(response)).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals", bbox=[135, 30, 145, 40]),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert result.metadata.coverage["spatial_scope_satisfied"] is expected

###############################################################################
@pytest.mark.asyncio
async def test_valid_empty_vector_result_satisfies_spatial_scope_for_bounded_request() -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="overpass",
        payload={"renderingMode": "clustered-points", "features": [], "totalResults": 0},
        result_type="features",
        result_status="valid_empty",
    )
    result = await _service(FakeProviderRegistry(response)).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals", bbox=[-145, -5, -135, 5]),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "valid_empty"
    assert result.metadata.coverage["spatial_scope_satisfied"] is True
    assert result.metadata.coverage["query_complete"] is True

###############################################################################
@pytest.mark.asyncio
async def test_provider_declared_circle_coverage_satisfies_spatial_scope() -> None:
    # A POI/landmark "around <place>" request may carry a narrow geocoder bbox
    # while the provider returns a wider radius-bounded set. The provider's
    # declared circle coverage is the authoritative spatial scope.
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="overpass",
        payload={
            "renderingMode": "geojson",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[12.48, 41.89], [12.50, 41.89], [12.50, 41.90], [12.48, 41.90], [12.48, 41.89]]
                        ],
                    },
                }
            ],
        },
        result_type="features",
        coverage={
            "type": "circle",
            "center": {"latitude": 41.8902, "longitude": 12.4922},
            "radius_m": 2500,
        },
    )
    result = await _service(FakeProviderRegistry(response)).execute_capability(
        ExecuteCapabilityInput(
            capability_id="places:hospitals",
            bbox=[12.492, 41.889, 12.493, 41.891],
            location_ref="colosseum",
        ),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert result.metadata.coverage["spatial_scope_satisfied"] is True

###############################################################################
@pytest.mark.asyncio
async def test_raster_result_without_scope_leaves_spatial_scope_unsatisfied() -> None:
    response = ProviderResponse(
        capability_id="places:hospitals",
        provider_id="fema",
        payload={"renderingMode": "raster-tile", "tileUrl": "https://example.test/export"},
        result_type="raster",
    )
    result = await _service(FakeProviderRegistry(response)).execute_capability(
        ExecuteCapabilityInput(capability_id="places:hospitals"),
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert result.metadata.coverage.get("spatial_scope_satisfied") is False

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
def test_solar_summary_exposes_bounded_pvgis_estimate() -> None:
    summary = _response_summary(
        ProviderResponse(
            capability_id="pvgis_solar",
            provider_id="pvgis",
            payload={
                "renderingMode": "metadata-only",
                "yearlyKwhPerKwpEstimate": 1267.38,
            },
            result_type="metadata",
        )
    )

    assert summary["solar_potential"] == {
        "yearly_kwh_per_kwp": 1267.38,
        "unit": "kWh/kWp/year",
    }

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

###############################################################################
def test_normalized_polygon_feature_is_renderable_and_has_bounds() -> None:
    summary = _response_summary(
        ProviderResponse(
            capability_id="noaa_weather_alerts",
            provider_id="noaa",
            payload={
                "renderingMode": "geojson",
                "features": [
                    {
                        "id": "alert-1",
                        "category": "weather_alert",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-95.6, 29.5],
                                    [-95.3, 29.5],
                                    [-95.3, 29.9],
                                    [-95.6, 29.9],
                                    [-95.6, 29.5],
                                ]
                            ],
                        },
                    }
                ],
            },
            result_type="features",
        )
    )

    assert summary["map_eligibility"] == "renderable"
    assert summary["bbox"] == [-95.6, 29.5, -95.3, 29.9]

# --- test_capability_router.py ---




###############################################################################
class _Runtime:

    # -------------------------------------------------------------------------
    def __init__(self, *, disabled: set[str] | None = None) -> None:
        self.disabled = disabled or set()

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return capability_id not in self.disabled

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return capability_id not in self.disabled

###############################################################################
def _router(runtime: _Runtime | None = None) -> CapabilityRouter:
    registry = CapabilityRegistry.from_catalog_snapshot(
        GeospatialManifestSnapshot(
        providers=(),
            basemaps=[
                {
                    "id": "osm_default",
                    "name": "OpenStreetMap",
                    "provider": "osm_tiles",
                    "capabilityKind": "basemap",
                    "agenticUse": {"domains": ["map_rendering"]},
                }
            ],
            overlays=[
                {
                    "id": "traffic",
                    "name": "Traffic",
                    "provider": "test",
                    "capabilityKind": "vector-overlay",
                    "description": "Traffic incidents",
                    "capabilities": ["traffic"],
                    "agenticUse": {"domains": ["data_retrieval"]},
                    "executionContract": {
                        "supported_operations": ["show", "inspect"],
                        "supported_scope_kinds": ["bbox"],
                        "temporal_modes": ["current"],
                        "render_support": "vector",
                        "coverage": "global",
                    },
                }
            ],
            cameras=[],
            transit=[],
            tools=[],
            runtime_profiles=(),
        )
    )
    return CapabilityRouter(
        capability_registry=registry,
        runtime_registry=cast(Any, runtime or _Runtime()),
    )

###############################################################################
def _state(*, active_map: bool = False) -> AgentRunState:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Show traffic.",
    )
    if active_map:
        state.active_map_session = cast(Any, object())
    return state

###############################################################################
def _route(**overrides: Any) -> CapabilityRoute:
    values: dict[str, Any] = {
        "primary_domain": CapabilityDomain.DATA_RETRIEVAL,
        "task_mode": "execute",
        "presentation": "map",
        "location_mode": "target",
        "capability_queries": ["traffic"],
    }
    values.update(overrides)
    return CapabilityRoute.model_validate(values)

###############################################################################
def test_router_shortlists_without_selecting_final_arguments() -> None:
    decision = _router().validate_route(
        _route(), user_message="Show traffic in Zurich.", active_state=_state()
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == ["traffic"]
    assert "radius_m" not in decision.route.model_dump()


###############################################################################
def test_router_normalizes_radius_scope_to_provider_bbox_after_location_resolution() -> None:
    state = _state()
    state.location_refs["austin"] = ResolvedLocation(
        label="Austin, Texas",
        latitude=30.2672,
        longitude=-97.7431,
        bbox=[-98.1, 29.9, -97.4, 30.6],
        country="United States",
    )

    decision = _router().validate_route(
        _route(
            operation="retrieve_features",
            spatial_scope={
                "kind": "radius",
                "relationship": "around",
                "target_refs": ["Austin"],
                "distance_m": 25000,
            },
        ),
        user_message="Show traffic around Austin.",
        active_state=state,
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == ["traffic"]


###############################################################################
def test_router_keeps_bbox_provider_for_point_framed_area_request() -> None:
    state = _state()
    state.location_refs["austin"] = ResolvedLocation(
        label="Austin, Texas",
        latitude=30.2672,
        longitude=-97.7431,
        bbox=[-98.1, 29.9, -97.4, 30.6],
        country="United States",
    )

    decision = _router().validate_route(
        _route(
            operation="retrieve_features",
            spatial_scope={"kind": "point", "target_refs": ["Austin"]},
        ),
        user_message="Show traffic at Austin.",
        active_state=state,
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == ["traffic"]


###############################################################################
def test_router_keeps_solar_estimate_on_metadata_only_text_route() -> None:
    state = _state()
    state.user_message = "Estimate PVGIS solar potential near Rome, Italy."
    state.location_refs["rome"] = ResolvedLocation(
        label="Rome, Italy",
        latitude=41.9028,
        longitude=12.4964,
        bbox=[12.35, 41.75, 12.65, 42.05],
        country="Italy",
    )
    router = CapabilityRouter(
        capability_registry=CapabilityRegistry(),
        runtime_registry=RuntimeRegistry(),
    )

    decision = router.validate_route(
        _route(
            secondary_domains=[
                CapabilityDomain.PLACE_SEARCH,
                CapabilityDomain.MAP_RENDERING,
            ],
            presentation="both",
            operation="estimate_solar_potential",
            capability_queries=[
                "pvgis solar potential",
                "solar irradiance estimate",
                "photovoltaic potential",
            ],
            spatial_scope={
                "kind": "radius",
                "relationship": "near",
                "target_refs": ["Rome"],
                "distance_m": 25000,
            },
        ),
        user_message=state.user_message,
        active_state=state,
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == ["pvgis_solar"]
    assert decision.route.presentation == "text"
    assert "metadata_only_analysis_route_normalized" in decision.reason_codes

###############################################################################
def test_router_rejects_answer_route_with_execution_intent() -> None:
    decision = _router().validate_route(
        CapabilityRoute(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            task_mode="answer",
            presentation="text",
            location_mode="none",
            capability_queries=["traffic"],
        ),
        user_message="Show traffic.",
        active_state=_state(),
    )

    assert decision.status == "rejected"
    assert "route_task_mode_requires_conversation_domain" in decision.reason_codes
    assert "route_task_mode_disallows_capability_queries" in decision.reason_codes

###############################################################################
def test_router_rejects_clarify_route_that_attempts_execution() -> None:
    decision = _router().validate_route(
        CapabilityRoute(
            primary_domain=CapabilityDomain.CONVERSATION,
            task_mode="clarify",
            presentation="text",
            location_mode="none",
            capability_queries=["traffic"],
            clarification_question="Which region do you mean?",
        ),
        user_message="Show traffic.",
        active_state=_state(),
    )

    assert decision.status == "rejected"
    assert "route_task_mode_disallows_capability_queries" in decision.reason_codes

###############################################################################
def test_router_rejects_hallucinated_ids_and_reports_no_capability() -> None:
    decision = _router().validate_route(
        _route(explicit_capability_ids=["not-in-catalog"]),
        user_message="Use not-in-catalog.",
        active_state=_state(),
    )

    assert decision.status == "no_capability"
    assert decision.rejected_capability_ids == ["not-in-catalog"]
    assert "unknown_capability_id" in decision.reason_codes

###############################################################################
def test_router_requires_active_map_for_map_state_follow_up() -> None:
    decision = _router().validate_route(
        _route(primary_domain=CapabilityDomain.MAP_STATE, location_mode="none"),
        user_message="Hide the layer.",
        active_state=_state(),
    )

    assert decision.status == "clarification"
    assert "active_map_required" in decision.reason_codes

###############################################################################
def test_router_does_not_require_a_place_for_basemap_switch_on_active_map() -> None:
    state = _state()
    state.active_map_session = cast(
        Any, SimpleNamespace(
            overlay_collection=SimpleNamespace(instances=[]),
            resolved_location=ResolvedLocation(label="Florence", latitude=43.77, longitude=11.25),
        )
    )
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_STATE,
            presentation="map",
            location_mode="target",
            operation="show",
            target_refs=["satellite basemap"],
        ),
        user_message="Now switch to satellite imagery",
        active_state=state,
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.location_mode == "none"
    assert decision.route.target_refs == []

###############################################################################
def test_router_handles_runtime_disabled_explicit_candidate() -> None:
    decision = _router(_Runtime(disabled={"traffic"})).validate_route(
        _route(explicit_capability_ids=["traffic"]),
        user_message="Show traffic.",
        active_state=_state(),
    )

    assert decision.status == "no_capability"
    assert decision.rejected_capability_ids == ["traffic"]
    assert "capability_disabled" in decision.reason_codes

###############################################################################
def test_router_opens_discovery_when_semantic_shortlist_is_empty() -> None:
    router = _router()
    router.capability_registry.shortlist = lambda **kwargs: []  # type: ignore[method-assign]

    decision = router.validate_route(
        _route(capability_queries=["obscure atmospheric index"]),
        user_message="Show an obscure atmospheric index.",
        active_state=_state(),
    )

    assert decision.status == "discovery_required"
    assert "discovery_required" in decision.reason_codes

###############################################################################
@pytest.mark.parametrize(
    "target,kept",
    [("Milan city center", []), ("Rome city centre", ["Rome city centre"])],
)
def test_zoom_on_the_shown_city_centre_is_not_a_new_place(target: str, kept: list[str]) -> None:
    state = _state()
    state.active_map_session = cast(
        Any, SimpleNamespace(
            overlay_collection=SimpleNamespace(instances=[]),
            resolved_location=ResolvedLocation(
                label="Milan, Lombardy, Italy", latitude=45.46, longitude=9.19
            ),
        )
    )
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_STATE,
            location_mode="target",
            capability_queries=[],
            operation="zoom_in",
            target_refs=[target],
        ),
        user_message=f"Zoom in on {target}",
        active_state=state,
    )

    assert decision.route.target_refs == kept
    assert decision.route.location_mode == "none"

###############################################################################
def test_map_state_route_naming_a_place_without_a_map_becomes_a_new_map() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_STATE,
            location_mode="target",
            capability_queries=[],
            target_refs=["satellite basemap", "Genoa, Italy"],
        ),
        user_message="Genoa, Italy",
        active_state=_state(),
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert decision.route.location_mode == "target"
    assert decision.route.target_refs == ["Genoa, Italy"]

###############################################################################
def test_basemap_inventory_question_is_limited_to_basemaps() -> None:
    decision = _router().validate_route(
        CapabilityRoute(
            primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
            task_mode="execute",
            presentation="text",
            capability_queries=["available maps"],
        ),
        user_message="Which basemaps are available?",
        active_state=_state(),
    )

    assert decision.route.operation == "discover_available_map_data"
    assert decision.route.capability_queries == ["basemap"]

###############################################################################
def test_broad_catalog_question_routes_to_unfiltered_capability_discovery() -> None:
    router = _router()
    router.capability_registry.shortlist = lambda **_kwargs: pytest.fail(  # type: ignore[method-assign]
        "catalog inventory must defer filtering until discovery"
    )
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
        secondary_domains=[CapabilityDomain.PLACE_SEARCH, CapabilityDomain.MAP_RENDERING],
        task_mode="execute",
        presentation="text",
        location_mode="target",
        capability_queries=["map data", "basemaps", "geospatial layers"],
        target_refs=["Florence, Italy"],
        spatial_scope={"kind": "point", "target_refs": ["Florence, Italy"]},
    )

    decision = router.validate_route(
        route,
        user_message=(
            "What map data can you show for Florence, Italy? "
            "Do not display a map or load a layer."
        ),
        active_state=_state(),
    )

    assert decision.status == "discovery_required"
    assert decision.route.operation == "discover_available_map_data"
    assert decision.route.capability_queries == []
    assert decision.capability_ids == []

###############################################################################
def test_router_clarifies_broad_infrastructure_category_before_shortlisting() -> None:
    for query in ("infrastructure", "infrastructure category", "infrastructure type"):
        decision = _router().validate_route(
            _route(
                operation="retrieve_infrastructure",
                capability_queries=[query],
            ),
            user_message=f"Show {query}.",
            active_state=_state(),
        )

        assert decision.status == "clarification"
        assert decision.capability_ids == []
        assert "ambiguous_infrastructure_category" in decision.reason_codes
        assert decision.clarification_question is not None
        assert "EV charging" in decision.clarification_question

###############################################################################
def test_raw_infrastructure_request_cannot_be_silently_guessed_into_subtype() -> None:
    decision = _router().validate_route(
        _route(
            operation="retrieve_infrastructure",
            capability_queries=["residential buildings"],
        ),
        user_message="Show infrastructure in Rome.",
        active_state=_state(),
    )

    assert decision.status == "clarification"
    assert decision.capability_ids == []
    assert "ambiguous_infrastructure_category" in decision.reason_codes

###############################################################################
def test_router_returns_boundary_limitation_without_replacing_active_map() -> None:
    state = _state(active_map=True)
    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        country="Switzerland",
    )
    active_map = state.active_map_session
    decision = _router().validate_route(
        _route(
            operation="show_boundary",
            capability_queries=["exact boundary"],
            spatial_scope={"kind": "administrative_geometry"},
        ),
        user_message="Show the exact boundary of Zurich.",
        active_state=state,
    )

    assert decision.status == "clarification"
    assert "unsupported_boundary_scope" in decision.reason_codes
    assert "active_map_preserved" in decision.reason_codes
    assert decision.clarification_question is not None
    assert "left the active map unchanged" in decision.clarification_question
    assert state.active_map_session is active_map

###############################################################################
def test_router_normalizes_new_map_location_prerequisite_and_hides_basemap_tools() -> None:
    decision = _router().validate_route(
        _route(location_mode="none"),
        user_message="Show traffic on a new map.",
        active_state=_state(),
    )

    assert decision.status == "accepted"
    assert decision.route.location_mode != "none"
    assert "location_required_for_new_map" in decision.reason_codes
    assert "osm_default" not in decision.capability_ids

###############################################################################
def test_location_map_fallback_route_is_limited_to_non_data_map_wording() -> None:
    fallback = build_location_map_fallback_route("Show me Springfield")

    assert fallback is not None
    assert fallback.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert fallback.secondary_domains == [CapabilityDomain.MAP_RENDERING]
    assert fallback.presentation == "map"
    assert fallback.location_mode != "none"

    assert build_location_map_fallback_route("Show hospitals near Springfield") is None

###############################################################################
@pytest.mark.parametrize("presentation", ["text", "map"])
@pytest.mark.parametrize("operation", ["remove_layer", "change_basemap"])
def test_router_uses_active_map_for_layer_lifecycle_updates(presentation: str, operation: str) -> None:
    state = _state(active_map=True)
    state.location_refs["current map"] = ResolvedLocation(
        label="Current map",
        latitude=35.0,
        longitude=139.0,
    )
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_STATE,
            presentation=presentation,
            location_mode="target",
            capability_queries=["remove overlay layer", "map layer management"],
            operation=operation,
            target_refs=["earthquake layer"],
        ),
        user_message="Remove the earthquake layer.",
        active_state=state,
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.location_mode == "none"
    assert decision.route.presentation in {"map", "both"}
    assert "active_map_update_uses_current_map" in decision.reason_codes

###############################################################################
def test_router_normalizes_data_bearing_add_layer_routes_after_active_map() -> None:
    state = _state(active_map=True)
    state.location_refs["japan"] = ResolvedLocation(
        label="Japan",
        latitude=36.5748,
        longitude=139.2394,
        bbox=[122.7, 20.2, 154.2, 45.7],
    )
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_STATE,
            operation="add_layer",
            capability_queries=["traffic"],
            target_refs=["Traffic"],
            spatial_scope={
                "kind": "administrative_geometry",
                "relationship": "around",
                "target_refs": ["Japan"],
            },
        ),
        user_message="Add traffic around Japan.",
        active_state=state,
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert "data_bearing_map_route_normalized" in decision.reason_codes

###############################################################################
def test_router_keeps_named_provider_layer_requests_executable() -> None:
    # "Add the RainViewer radar to this map" names a provider, but it asks for
    # that provider's data on the map; execute must be allowed for that route.
    state = _state(active_map=True)
    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich, Switzerland", latitude=47.37, longitude=8.54
    )
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
            secondary_domains=(CapabilityDomain.MAP_RENDERING,),
            operation="add_layer",
            capability_queries=["rainviewer precipitation radar"],
        ),
        user_message="Add the RainViewer precipitation radar to this map.",
        active_state=state,
    )

    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert "data_bearing_map_route_normalized" in decision.reason_codes

###############################################################################
def test_router_normalizes_new_data_bearing_map_routes() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_RENDERING,
            operation="add_layer",
            capability_queries=["land cover"],
            target_refs=["Mount Etna"],
            spatial_scope={
                "kind": "administrative_geometry",
                "relationship": "around",
                "target_refs": ["Mount Etna"],
            },
        ),
        user_message="Show land cover around Mount Etna.",
        active_state=_state(),
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert "data_bearing_map_route_normalized" in decision.reason_codes

###############################################################################
def test_router_keeps_data_retrieval_on_poi_map_search_route() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            operation="search_places",
            capability_queries=["place search", "overpass_poi_amenities"],
        ),
        user_message="Show pharmacies in Rome, Italy.",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert CapabilityDomain.MAP_RENDERING in decision.route.secondary_domains
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert "data_bearing_place_search_route_normalized" in decision.reason_codes
    assert "location_map_route_normalized" not in decision.reason_codes

###############################################################################
def test_router_adds_data_retrieval_to_text_only_poi_search_route() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            presentation="text",
            operation="search_places",
            capability_queries=["pharmacy"],
        ),
        user_message=(
            "Find nearby pharmacies within about 2 km of the Colosseum in Rome. "
            "Return names and distances as text."
        ),
        active_state=_state(),
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert CapabilityDomain.MAP_RENDERING not in decision.route.secondary_domains
    assert "data_bearing_place_search_route_normalized" in decision.reason_codes

###############################################################################
def test_router_keeps_text_only_coordinate_lookup_free_of_provider_data() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            presentation="text",
            operation="retrieve",
            capability_queries=["coordinates"],
        ),
        user_message=(
            "What are the coordinates of the Colosseum in Rome? Give latitude "
            "and longitude as text only; don't load a map."
        ),
        active_state=_state(),
    )

    assert decision.status == "accepted"
    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert decision.route.secondary_domains == []
    assert decision.route.operation == "resolve_location"
    assert decision.route.capability_queries == []
    assert decision.route.location_mode != "none"
    assert decision.capability_ids == []
    assert "text_only_coordinate_lookup_route_normalized" in decision.reason_codes

###############################################################################
def test_router_normalizes_saved_evidence_inspection_without_provider_lookup() -> None:
    state = _state()
    state.evidence_refs = ["evidence-previous"]
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            presentation="text",
            operation="retrieve",
            location_mode="target",
            capability_queries=["pharmacy near the Colosseum"],
            target_refs=["Colosseum", "pharmacies"],
            filters={"category": "pharmacy"},
        ),
        user_message=(
            "Inspect the evidence from the immediately preceding pharmacy lookup. "
            "Use saved results only and do not fetch again or render a map."
        ),
        active_state=state,
    )

    assert decision.status == "accepted"
    assert decision.route.primary_domain is CapabilityDomain.DATA_RETRIEVAL
    assert decision.route.secondary_domains == []
    assert decision.route.operation == "inspect_evidence"
    assert decision.route.capability_queries == []
    assert decision.route.explicit_capability_ids == []
    assert decision.route.location_mode == "none"
    assert decision.route.spatial_scope is None
    assert decision.route.target_refs == []
    assert decision.route.filters == {}
    assert decision.capability_ids == []
    assert "text_evidence_inspection_route_normalized" in decision.reason_codes

###############################################################################
def test_router_does_not_assume_evidence_exists_in_a_new_conversation() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            presentation="text",
            operation="retrieve",
            capability_queries=["evidence from the previous pharmacy lookup"],
        ),
        user_message="Inspect evidence from the previous pharmacy lookup.",
        active_state=_state(),
    )

    assert decision.route.operation == "retrieve"
    assert "text_evidence_inspection_route_normalized" not in decision.reason_codes


###############################################################################
def test_router_normalizes_geocoding_route_for_location_only_map() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            operation="resolve_place",
            capability_queries=[
                "place search",
                "geocoding",
                "reverse geocoding",
            ],
        ),
        user_message="35.6762, 139.6503",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert decision.route.secondary_domains == []
    assert decision.route.operation == "show_location_on_map"
    assert decision.route.capability_queries == ["place search", "map viewport"]
    assert "location_map_route_normalized" in decision.reason_codes

###############################################################################
def test_router_normalizes_named_landmark_map_route() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            operation="show_on_map",
            capability_queries=[
                "place search",
                "landmark lookup",
                "map view of a named feature",
            ],
        ),
        user_message="Show Table Mountain near Cape Town, South Africa on the map.",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert decision.route.operation == "show_location_on_map"
    assert decision.route.capability_queries == ["place search", "map viewport"]
    assert "location_map_route_normalized" in decision.reason_codes

###############################################################################
def test_router_preserves_explicit_poi_landmark_lookup() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            operation="locate",
            capability_queries=["place search", "poi"],
        ),
        user_message="Locate the Acropolis Museum in Athens, Greece.",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert decision.route.operation == "locate"
    assert decision.route.capability_queries == ["place search", "poi"]
    assert "location_map_route_normalized" not in decision.reason_codes

###############################################################################
def test_router_normalizes_undated_recent_historical_scope_to_current() -> None:
    decision = _router().validate_route(
        _route(
            temporal_scope={"mode": "historical", "granularity": "recent"}
        ),
        user_message="Show recent traffic in Zurich.",
        active_state=_state(),
    )

    assert decision.status == "accepted"
    assert decision.route.temporal_scope.mode == "current"
    assert "recent_scope_normalized_to_current" in decision.reason_codes

###############################################################################
def test_router_normalizes_undated_recent_aggregation_scope_to_current() -> None:
    decision = _router().validate_route(
        _route(
            temporal_scope={
                "mode": "historical",
                "granularity": "none",
                "aggregation": "recent",
            }
        ),
        user_message="Show recent earthquakes around Tokyo.",
        active_state=_state(),
    )

    assert decision.status == "accepted"
    assert decision.route.temporal_scope.mode == "current"
    assert "recent_scope_normalized_to_current" in decision.reason_codes

###############################################################################
def test_router_preserves_dated_historical_scope() -> None:
    decision = _router().validate_route(
        _route(
            temporal_scope={
                "mode": "historical",
                "granularity": "day",
                "start_time_iso": "2026-09-01T00:00:00Z",
                "end_time_iso": "2026-09-02T00:00:00Z",
            }
        ),
        user_message="Show traffic from September 1.",
        active_state=_state(),
    )

    assert decision.status == "discovery_required"
    assert decision.route.temporal_scope.mode == "historical"
    assert "recent_scope_normalized_to_current" not in decision.reason_codes


###############################################################################
@pytest.mark.parametrize("mode,refs,analysis", [
    ("none", ["Europe"], {"kind": "rank", "metric": "precipitation"}),
    ("target", ["Europe"], {"kind": "rank", "metric": "precipitation"}),
    ("search_area", [], {"kind": "hotspot", "metric": "count"}),
])
def test_router_normalizes_discovery_area(mode: str, refs: list[str], analysis: dict[str, str]) -> None:
    decision = _router().validate_route(
        _route(location_mode=mode, target_refs=refs, analysis=analysis),
        user_message="Where did it rain most?", active_state=_state(),
    )
    assert decision.route.location_mode == "search_area"
    assert decision.route.target_refs == (refs or ["World"])
    assert decision.route.spatial_scope is not None
    assert decision.route.spatial_scope.kind == "bbox"
    assert decision.route.spatial_scope.relationship == "in"


###############################################################################
def test_location_fallback_does_not_swallow_analysis_query() -> None:
    assert build_location_map_fallback_route("Show me where in Europe it rained most") is None
