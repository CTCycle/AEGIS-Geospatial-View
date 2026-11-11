from __future__ import annotations
from collections import deque
import json
import pytest
import asyncio
from typing import Any
from server.domain.agent.capability_route import AgentGoal, AgentPhase, AgentRunState, AgentSpatialScope, AgentTemporalScope, CapabilityRoute, CompletionContract
from server.domain.agent.decision import ResolvedLocation, ClarificationRequest
from server.domain.agent.evidence import AgentEvidenceSummary
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.geospatial.providers import ProviderResponse
from server.domain.llm.types import LLMResult, LLMToolCall, LLMToolDefinition
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.native_tools import register_agent_tools, _bind_execute_request
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry, route_target_location_available, _data_obligation_unmet
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.agent.location_resolver import LocationResolver, find_macro_region
from server.services.geospatial.providers.base import ProviderUnavailableError
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from server.contracts.location import LocationSignal
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult, ToolExecutionError
from server.services.agent.capability_execution import _provider_params
from server.services.agent.completion import layer_edit_count, presentation_contract
from server.services.agent.completion import CompletionEvaluator, ledger_outcomes
from server.domain.agent.task_ledger import merge_ledger
from server.services.agent.tool_definitions import ExecuteCapabilityInput, TransformEvidenceInput, CapabilityDiscoveryInput, RouteRequestInput
from server.services.agent.tool_handlers.evidence import EvidenceToolHandler, _apply_operations, _inspect_payload
from server.services.catalog.loader import load_macro_regions
from pydantic import BaseModel
from server.domain.agent.tools import RegisteredTool
from server.services.agent.tool_handlers.catalog import CatalogToolHandler

# --- test_native_gibs_trajectory.py ---





###############################################################################
class _ScriptedProvider:

    # -------------------------------------------------------------------------
    def __init__(self, results: list[LLMResult]) -> None:
        self._results = deque(results)

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        del request, kwargs
        return self._results.popleft()


###############################################################################
class _ProviderFactory:

    # -------------------------------------------------------------------------
    def __init__(self, provider: _ScriptedProvider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> _ScriptedProvider:
        del provider
        return self.provider


###############################################################################
class _FakeLocationResolver:

    # -------------------------------------------------------------------------
    async def resolve_location_signals(
        self, signals: Any, memory_snapshot: Any
    ) -> ResolvedLocation:
        del signals, memory_snapshot
        return ResolvedLocation(
            label="Rome, Italy",
            latitude=41.9028,
            longitude=12.4964,
            country="Italy",
            city="Rome",
            source="scripted-test",
            confidence=1.0,
            location_type="city",
        )


###############################################################################
class _FakeProviderRegistry:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.requests: list[Any] = []

    # -------------------------------------------------------------------------
    async def fetch(self, provider_id: str, request: Any) -> ProviderResponse:
        self.requests.append((provider_id, request))
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=provider_id,
            payload={
                "renderingMode": "wms",
                "serviceUrl": "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
                "layerId": "SRTM_Color_Index",
                "layers": "SRTM_Color_Index",
                "format": "image/png",
            },
            attribution=["© NASA GIBS"],
            result_status="ok",
            result_type="raster",
            source_url="https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
        )


###############################################################################
class _FakeEvidenceRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self._records: dict[str, tuple[AgentEvidenceSummary, bytes]] = {}

    # -------------------------------------------------------------------------
    def create(
        self,
        *,
        conversation_id: str,
        run_id: str | None,
        kind: Any,
        media_type: str,
        status: Any,
        payload: Any,
        summary: dict[str, Any],
        provenance: dict[str, Any],
        parent_evidence_ids: list[str] | None = None,
    ) -> AgentEvidenceSummary:
        del conversation_id, run_id, parent_evidence_ids
        evidence_id = "evidence-srtm-color-index"
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        record = AgentEvidenceSummary(
            evidence_id=evidence_id,
            kind=kind,
            media_type=media_type,
            status=status,
            summary=dict(summary),
            provenance=dict(provenance),
            byte_size=len(raw),
            map_eligibility="renderable",
        )
        self._records[evidence_id] = (record, raw)
        return record

    # -------------------------------------------------------------------------
    def get_summary(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> AgentEvidenceSummary | None:
        del conversation_id
        record = self._records.get(evidence_id)
        return record[0] if record else None

    # -------------------------------------------------------------------------
    def get_payload(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> tuple[AgentEvidenceSummary, bytes] | None:
        del conversation_id
        return self._records.get(evidence_id)


###############################################################################
def _call(call_id: str, name: str, arguments: dict[str, Any]) -> LLMResult:
    return LLMResult(
        content="",
        tool_calls=[LLMToolCall(id=call_id, name=name, arguments=arguments)],
    )


###############################################################################
@pytest.mark.asyncio
async def test_manifest_backed_gibs_layer_reaches_map_preparation() -> None:
    capability_registry = CapabilityRegistry()
    runtime_registry = RuntimeRegistry(
        catalog_snapshot=capability_registry.catalog_snapshot,
        credentials_repo=None,
    )
    assert capability_registry.get_capability("SRTM_Color_Index") is not None
    assert runtime_registry.is_enabled("SRTM_Color_Index")
    assert runtime_registry.access_available("SRTM_Color_Index")

    provider_registry = _FakeProviderRegistry()
    evidence_repository = _FakeEvidenceRepository()
    registry = ToolRegistry(runtime_registry=runtime_registry)
    register_agent_tools(
        registry,
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
        provider_registry=provider_registry,  # type: ignore[arg-type]
        evidence_repository=evidence_repository,  # type: ignore[arg-type]
        location_resolver=_FakeLocationResolver(),  # type: ignore[arg-type]
        geospatial_api_service=object(),
    )
    provider = _ScriptedProvider(
        [
            _call(
                "route-1",
                "route_request",
                {
                    "primary_domain": "data_retrieval",
                    "secondary_domains": ["map_rendering"],
                    "task_mode": "execute",
                    "presentation": "map",
                    "location_mode": "target",
                    "capability_queries": ["SRTM_Color_Index"],
                    "operation": "show",
                    "target_refs": ["rome-italy"],
                },
            ),
            _call(
                "location-1",
                "resolve_geospatial_location",
                {
                    "target_id": "rome-italy",
                    "query": "Rome, Italy",
                    "expected_location_type": "city",
                },
            ),
            _call(
                "describe-1",
                "describe_geospatial_capability",
                {"capability_id": "SRTM_Color_Index"},
            ),
            _call(
                "execute-1",
                "execute_geospatial_capability",
                {"capability_id": "SRTM_Color_Index", "arguments": {}},
            ),
            _call(
                "map-1",
                "apply_map_plan",
                {
                    "expected_collection_revision": 0,
                    "actions": [
                        {"action": "set_basemap", "capability_id": "osm_default"},
                        {
                            "action": "add_evidence_layer",
                            "evidence_ref": "evidence-srtm-color-index",
                            "capability_id": "SRTM_Color_Index",
                            "visible": True,
                            "opacity": 0.68,
                        },
                    ],
                },
            ),
        ]
    )
    policy_engine = PolicyEngine(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    loop = AgentLoop(
        provider_factory=_ProviderFactory(provider),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(
            capability_registry=capability_registry,
            runtime_registry=runtime_registry,
        ),
        tool_registry=registry,
        tool_executor=ToolExecutor(
            tool_registry=registry,
            policy_engine=policy_engine,
        ),
    )
    state = AgentRunState(
        request_id="gibs-trajectory-request",
        conversation_id="gibs-trajectory-conversation",
        phase=AgentPhase.RECEIVE_REQUEST,
        user_message="Show the NASA GIBS SRTM color index over Rome, Italy.",
    )

    outcome = await loop.run(
        AgentLoopRequest(
            provider="scripted",
            model="scripted-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
    )

    assert outcome.stopped_reason == "awaiting_render"
    assert outcome.state.route is not None
    assert "SRTM_Color_Index" in outcome.state.capability_ids
    assert outcome.state.location_refs["rome-italy"].city == "Rome"
    assert "evidence-srtm-color-index" in outcome.state.evidence_refs
    assert outcome.state.prepared_map_session is not None
    assert outcome.state.prepared_map_session.basemap_id == "osm_default"
    overlay = outcome.state.prepared_map_session.overlay_collection.instances[-1]
    assert overlay.capability_id == "SRTM_Color_Index"
    assert overlay.descriptor["url"].startswith(
        "/api/geospatial/tiles/SRTM_Color_Index/"
    )
    assert [result.tool_name for result in outcome.tool_results] == [
        "resolve_geospatial_location",
        "describe_geospatial_capability",
        "execute_geospatial_capability",
        "apply_map_plan",
    ]
    assert all(result.status == "success" for result in outcome.tool_results)
    assert provider_registry.requests[0][0] == "gibs"
    assert provider_registry.requests[0][1].capability_id == "SRTM_Color_Index"

# --- test_native_discovery_trajectories.py ---

"""Intent discovery using the real route, registry, execution and map boundaries."""





###############################################################################
class MemoryEvidence:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.records: dict[str, tuple[AgentEvidenceSummary, bytes]] = {}

    # -------------------------------------------------------------------------
    def create(self, **kwargs: Any) -> AgentEvidenceSummary:
        ref = f"evidence-{len(self.records) + 1}"
        raw = json.dumps(kwargs["payload"]).encode()
        summary = AgentEvidenceSummary(
            evidence_id=ref, kind=kwargs["kind"], media_type=kwargs["media_type"],
            status=kwargs["status"], summary=kwargs["summary"], provenance=kwargs["provenance"],
            byte_size=len(raw), map_eligibility=kwargs["summary"].get("map_eligibility", "renderable"),
        )
        self.records[ref] = summary, raw
        return summary

    # -------------------------------------------------------------------------
    def get_payload(self, ref: str, **kwargs: Any) -> tuple[AgentEvidenceSummary, bytes] | None:
        return self.records.get(ref)

    # -------------------------------------------------------------------------
    def get_summary(self, ref: str, **kwargs: Any) -> AgentEvidenceSummary | None:
        record = self.records.get(ref)
        return record[0] if record else None


###############################################################################
class DiscoveryProvider:

    # -------------------------------------------------------------------------
    def __init__(self, *, partial: bool = False) -> None:
        self.requests: list[Any] = []
        self.partial = partial

    # -------------------------------------------------------------------------
    async def fetch(self, provider: str, request: Any) -> ProviderResponse:
        self.requests.append(request)
        seismic = provider == "usgs"
        field = "magnitude" if seismic else "precipitation_sum_mm"
        latitude = request.params.get("latitude", 48.0) if request.params.get("sampling") != "area" and not seismic else 48.0
        longitude = request.params.get("longitude", 8.0) if request.params.get("sampling") != "area" and not seismic else 8.0
        return ProviderResponse(
            capability_id=request.capability_id, provider_id=provider,
            payload={"features": [
                {"latitude": latitude, "longitude": longitude, field: 9.0},
                {"latitude": 47.0 if seismic else latitude, "longitude": 9.0 if seismic else longitude, field: 100.0},
            ], "value_kind": "observation" if seismic else "model_estimate"},
            result_type="features", result_status="partial" if self.partial else "ok",
            partial=self.partial, units={field: "M" if seismic else "mm"},
            coverage={"bbox": list(request.bbox) if request.bbox else [longitude, latitude, longitude, latitude], "type": "grid_sample", "point_count": 2,
                      "spatial_scope_satisfied": True, "temporal_scope_satisfied": True},
        )


###############################################################################
def make_loop(
    model: _ScriptedProvider, providers: Any, resolver: Any = None, evidence: MemoryEvidence | None = None
) -> AgentLoop:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(catalog_snapshot=capabilities.catalog_snapshot, credentials_repo=None)
    registry = ToolRegistry(runtime_registry=runtime)
    register_agent_tools(registry, capability_registry=capabilities, runtime_registry=runtime,
                         provider_registry=providers, evidence_repository=evidence or MemoryEvidence(),
                         geospatial_api_service=object(), location_resolver=resolver or LocationResolver())
    return AgentLoop(provider_factory=_ProviderFactory(model),
                     capability_router=CapabilityRouter(capability_registry=capabilities, runtime_registry=runtime),
                     tool_registry=registry, tool_executor=ToolExecutor(tool_registry=registry,
                     policy_engine=PolicyEngine(capability_registry=capabilities, runtime_registry=runtime)))


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("place", ["Springfield", "Florence"])
async def test_ambiguous_place_still_clarifies(place: str) -> None:

    ###############################################################################
    class Resolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, *args: Any, **kwargs: Any) -> ClarificationRequest:
            return ClarificationRequest(question=f"Which {place}?", reason="Ambiguous place", missing_fields=["location"])
    model = _ScriptedProvider([
        _call("route", "route_request", {"primary_domain": "place_search", "task_mode": "execute",
              "presentation": "map", "location_mode": "target", "operation": "show_location_on_map", "target_refs": [place]}),
        _call("resolve", "resolve_geospatial_location", {"query": place, "target_id": place}),
    ])
    value = AgentRunState(phase=AgentPhase.RECEIVE_REQUEST, request_id="ambiguity", conversation_id="ambiguity", user_message=f"Show {place}")
    result = await make_loop(model, DiscoveryProvider(), Resolver()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=value, budget=AgentExecutionBudget(total_seconds=10)))
    assert result.stopped_reason == "clarification_required"
    assert value.prepared_map_session is None


###############################################################################
@pytest.mark.asyncio
async def test_direct_paris_weather_map_is_unchanged() -> None:

    ###############################################################################
    class Resolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, *args: Any, **kwargs: Any) -> ResolvedLocation:
            return ResolvedLocation(label="Paris", latitude=48.85, longitude=2.35, bbox=[2.2, 48.8, 2.5, 48.9])
    model = _ScriptedProvider([
        _call("route", "route_request", {"primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "map",
              "location_mode": "target", "operation": "show", "target_refs": ["Paris"],
              "capability_queries": ["weather"], "explicit_capability_ids": ["openmeteo_weather_forecast"]}),
        _call("resolve", "resolve_geospatial_location", {"query": "Paris", "target_id": "Paris"}),
        _call("execute", "execute_geospatial_capability", {"capability_id": "openmeteo_weather_forecast"}),
        _call("map", "apply_map_plan", {"expected_collection_revision": 0, "actions": [
            {"action": "set_basemap", "capability_id": "osm_default"},
            {"action": "add_evidence_layer", "capability_id": "openmeteo_weather_forecast", "evidence_ref": "evidence-1"}]}),
    ])
    value = AgentRunState(phase=AgentPhase.RECEIVE_REQUEST, request_id="paris", conversation_id="paris", user_message="Weather in Paris on a map")
    result = await make_loop(model, DiscoveryProvider(), Resolver()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=value, budget=AgentExecutionBudget(total_seconds=10)))
    assert result.stopped_reason == "awaiting_render"
    assert value.route.location_mode == "target"
    assert not any(r.tool_name == "transform_evidence" for r in result.tool_results)


###############################################################################
@pytest.mark.asyncio
async def test_failed_discovery_provider_has_no_map() -> None:

    ###############################################################################
    class FailingProvider:

        # -------------------------------------------------------------------------
        async def fetch(self, *args: Any, **kwargs: Any) -> ProviderResponse:
            raise ProviderUnavailableError("unavailable")
    model = _ScriptedProvider([
        _call("route", "route_request", {"primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "map",
              "location_mode": "search_area", "target_refs": ["Europe"], "capability_queries": ["weather"],
              "explicit_capability_ids": ["openmeteo_weather_forecast"], "analysis": {"kind": "rank", "metric": "temperature"}}),
        _call("execute", "execute_geospatial_capability", {"capability_id": "openmeteo_weather_forecast"}),
        LLMResult(content="The provider is unavailable; evidence is insufficient."),
    ])
    value = AgentRunState(phase=AgentPhase.RECEIVE_REQUEST, request_id="failure", conversation_id="failure", user_message="Where in Europe is it hottest?")
    result = await make_loop(model, FailingProvider()).run(AgentLoopRequest(provider="scripted", model="scripted",
        state=value, budget=AgentExecutionBudget(total_seconds=10)))
    assert result.stopped_reason == "insufficient_evidence"
    assert value.prepared_map_session is None


###############################################################################
@pytest.mark.asyncio
async def test_stale_lyon_does_not_bind_italy_search_area() -> None:

    ###############################################################################
    class Resolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, *args: Any, **kwargs: Any) -> ResolvedLocation:
            return ResolvedLocation(label="Italy", latitude=42, longitude=12, bbox=[6, 36, 19, 47])
    model = _ScriptedProvider([
        _call("route", "route_request", {"primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "map",
              "location_mode": "search_area", "target_refs": ["Italy"], "capability_queries": ["weather"],
              "analysis": {"kind": "rank", "metric": "temperature"}}),
        _call("resolve", "resolve_geospatial_location", {"query": "Italy", "target_id": "Italy", "expected_location_type": "country"}),
        LLMResult(content="I still need to retrieve and analyze weather evidence."),
    ])
    providers = DiscoveryProvider()
    value = AgentRunState(phase=AgentPhase.RECEIVE_REQUEST, request_id="stale", conversation_id="stale",
                          user_message="Where in Italy is it hottest?", context_hydrated=True,
                          location_refs={"lyon": ResolvedLocation(label="Lyon", latitude=45.75, longitude=4.85)})
    result = await make_loop(model, providers, Resolver()).run(AgentLoopRequest(provider="scripted", model="scripted",
        state=value, budget=AgentExecutionBudget(total_seconds=10), max_no_progress_corrections=0))
    assert result.tool_results[0].tool_name == "resolve_geospatial_location"
    assert any(location.label == "Italy" for location in value.location_refs.values())
    assert not providers.requests
    # The unfinished data work is recorded as blocked with the stop reason, not dropped.
    outcomes = ledger_outcomes(value, AgentLoop.completion_summary(value), now=datetime.now(UTC))
    assert {(item.kind, item.status, item.reason) for item in outcomes} == {
        ("location", "completed", None), ("data", "blocked", "insufficient_evidence"),
        ("analysis", "blocked", "insufficient_evidence"), ("presentation", "blocked", "insufficient_evidence")}


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("area,seismic,partial", [("Europe", False, False), (None, False, False),
                                                 ("Europe", True, False), ("Europe", False, True)])
async def test_discovery_reaches_derived_map_without_location_turn(area: str | None, seismic: bool, partial: bool) -> None:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(catalog_snapshot=capabilities.catalog_snapshot, credentials_repo=None)
    providers = DiscoveryProvider(partial=partial)
    evidence = MemoryEvidence()
    registry = ToolRegistry(runtime_registry=runtime)
    register_agent_tools(registry, capability_registry=capabilities, runtime_registry=runtime,
                         provider_registry=providers, evidence_repository=evidence,
                         geospatial_api_service=object(), location_resolver=LocationResolver())  # type: ignore[arg-type]
    capability = "usgs_earthquakes" if seismic else "openmeteo_weather_forecast"
    field = "magnitude" if seismic else "precipitation_sum_mm"
    operations = ([{"op": "grid_aggregate", "cell_size_deg": 2, "value_field": field, "order_by": "count"}]
                  if seismic else [{"op": "sort", "field": field, "descending": True}, {"op": "limit", "value": 1}])
    route = {"primary_domain": "data_retrieval", "secondary_domains": ["map_rendering"],
             "task_mode": "execute", "presentation": "map", "location_mode": "target" if area else "none",
             "target_refs": [area] if area else [], "capability_queries": ["earthquake" if seismic else "weather"],
             "explicit_capability_ids": [capability], "operation": "show",
             "analysis": {"kind": "hotspot" if seismic else "rank", "metric": field, "top_k": 1},
             "temporal_scope": {"mode": "current", "granularity": "week" if seismic else "day"}}
    model = _ScriptedProvider([
        _call("route", "route_request", route),
        _call("execute", "execute_geospatial_capability", {"capability_id": capability}),
        _call("transform", "transform_evidence", {"evidence_refs": ["evidence-1"], "operations": operations}),
        _call("map", "apply_map_plan", {"expected_collection_revision": 0, "actions": [
            {"action": "set_basemap", "capability_id": "osm_default"},
            {"action": "add_evidence_layer", "capability_id": capability, "evidence_ref": "evidence-2",
             "value_encoding": {"mode": "graduated", "field": "count" if seismic else field}},
            {"action": "set_viewport", "strategy": "fit_evidence", "evidence_refs": ["evidence-2"]},
        ]}),
    ])
    loop = AgentLoop(provider_factory=_ProviderFactory(model),  # type: ignore[arg-type]
                     capability_router=CapabilityRouter(capability_registry=capabilities, runtime_registry=runtime),
                     tool_registry=registry, tool_executor=ToolExecutor(tool_registry=registry,
                     policy_engine=PolicyEngine(capability_registry=capabilities, runtime_registry=runtime)))
    state = AgentRunState(request_id="discovery", conversation_id="discovery", phase=AgentPhase.RECEIVE_REQUEST,
                          user_message="Show where in Europe it rained most today" if area else "Show global weather extremes")
    result = await loop.run(AgentLoopRequest(provider="scripted", model="scripted", state=state,
                            budget=AgentExecutionBudget(total_seconds=15, hard_max_seconds=15)))
    assert result.stopped_reason == "awaiting_render", [(r.tool_name, r.status, r.error) for r in result.tool_results]
    assert not any(r.tool_name == "resolve_geospatial_location" for r in result.tool_results)
    assert state.route is not None and state.route.location_mode == "search_area"
    assert (area or "World") in state.location_refs
    assert providers.requests[0].params["sampling"] == "area" if not seismic else "sampling" not in providers.requests[0].params
    if seismic:
        assert providers.requests[0].time is not None
    else:
        # Current-day weather starts at each point's local midnight, rather
        # than a synthesized rolling-day timestamp.
        assert providers.requests[0].time is None
    assert state.prepared_map_session is not None
    descriptor = state.prepared_map_session.overlay_collection.instances[-1].descriptor
    assert descriptor["value_encoding"]["max"] == (1 if seismic else 100)
    # One derived point fits at city scale rather than maximum zoom.
    viewport_bbox = state.prepared_map_session.viewport.bbox
    assert viewport_bbox is not None and min(viewport_bbox[2] - viewport_bbox[0], viewport_bbox[3] - viewport_bbox[1]) >= 0.25
    assert evidence.records["evidence-2"][0].provenance["units"][field]

# --- test_discovery_contracts.py ---





###############################################################################
def state(area: str = "Europe") -> AgentRunState:
    value = AgentRunState(request_id="test", conversation_id="test", phase=AgentPhase.BUILD_TOOL_CONTEXT,
                          user_message="Where is it hottest?")
    value.route = CapabilityRoute(primary_domain=CapabilityDomain.DATA_RETRIEVAL, task_mode="execute",
                                  presentation="map", location_mode="search_area", target_refs=[area],
                                  analysis={"kind": "rank", "metric": "temperature"})
    return value


###############################################################################
@pytest.mark.asyncio
async def test_macro_region_never_geocodes() -> None:
    geocoder = AsyncMock()
    result = await LocationResolver(nominatim_service=geocoder).resolve_location_signals(
        [LocationSignal(signal_type="region", raw_value="Europe")], {})
    assert result.location_type == "macro_region"
    assert result.bbox == [-25, 34, 45, 72]
    assert not geocoder.search.await_count
    assert find_macro_region("Western Europe") is not None
    assert all(find_macro_region(name) is None for name in ["Georgia", "Springfield", "Florence", "America"])


###############################################################################
def test_duplicate_macro_alias_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "reference").mkdir()
    region = {"id": "a", "name": "A", "aliases": ["shared"], "bbox": [-10, 0, 10, 10], "kind": "subregion"}
    (tmp_path / "reference/macro_regions.json").write_text(json.dumps({"macro_regions": [region, {**region, "id": "b", "name": "B"}]}))
    with pytest.raises(ValueError, match="Duplicate macro-region alias"):
        load_macro_regions(tmp_path)


###############################################################################
@pytest.mark.parametrize("area", ["Europe", "World"])
def test_binding_owns_sampling_extent_and_recent_window(area: str) -> None:
    value = state(area)
    value.route = CapabilityRoute.model_validate({**value.route.model_dump(), "temporal_scope": {"mode": "current", "granularity": "week"}})
    value.route = value.route.model_copy(update={"spatial_scope": AgentSpatialScope(kind="bbox", relationship="in", target_refs=[area])})
    AgentLoop._bind_search_area(value, value.route)
    AgentLoop._compile_native_goal(value, value.route)
    bound = _bind_execute_request(ExecuteCapabilityInput(capability_id="weather", arguments={"sampling": "point"}), value)
    assert bound.bbox == find_macro_region(area).bbox
    assert bound.arguments["sampling"] == "area"
    assert 6.99 < (datetime.now(UTC) - datetime.fromisoformat(bound.start_time_iso)).total_seconds() / 86400 < 7.01
    assert _provider_params(bound, manifest={"executionContract": {"supported_scope_kinds": ["grid_sample"]}})["sampling"] == "area"
    assert "sampling" not in _provider_params(bound, manifest={})
    value.goal.location_mode = "target"
    assert "sampling" not in _bind_execute_request(ExecuteCapabilityInput(capability_id="weather", arguments={"sampling": "area"}), value).arguments


###############################################################################
def test_stale_location_and_analysis_map_gate() -> None:
    value = state("Italy")
    value.location_refs["lyon"] = find_macro_region("Europe").model_copy(update={"label": "Lyon"})
    assert not route_target_location_available(value)
    assert not ToolRegistry._prerequisites_satisfied(frozenset({"location_if_required"}), value)
    value = state()
    AgentLoop._bind_search_area(value, value.route)
    assert ToolRegistry._prerequisites_satisfied(frozenset({"location_if_required"}), value)
    assert not ToolRegistry._prerequisites_satisfied(frozenset({"analysis_complete_if_required"}), value)
    value.tool_results.append(ToolResult(call_id="transform", tool_name="transform_evidence", status="success", summary="ranked",
                                      data={"located_record_count": 1}, metadata=ToolExecutionMetadata(duration_ms=0)))
    assert ToolRegistry._prerequisites_satisfied(frozenset({"analysis_complete_if_required"}), value)


###############################################################################
def test_text_stop_is_no_progress_while_derived_locations_are_pending() -> None:
    value = state()
    value.context_hydrated = True
    AgentLoop._bind_search_area(value, value.route)
    AgentLoop._compile_native_goal(value, value.route)
    assert "result_locations_derived" in AgentLoop._pending_native_requirements(value)
    assert AgentLoop._evaluate_text_stop(value, value.route, "Done", available_tools=["transform_evidence"])[0] == "no_progress"


###############################################################################
def test_compound_obligations_need_covering_evidence() -> None:
    def executed(capability_id: str, covered: list[str]) -> ToolResult:
        return ToolResult(call_id=capability_id, tool_name="execute_geospatial_capability", status="success", summary="ok",
                          evidence_refs=[f"evidence_{capability_id}"],
                          metadata=ToolExecutionMetadata(duration_ms=0, capability_id=capability_id, covered_queries=covered))

    value = state()
    value.route.capability_queries = ["weather", "earthquakes"]
    value.completion_contract = CompletionContract(operation="rank", data_requirement="provider_data",
                                                   data_obligations=["weather", "earthquakes"])
    value.tool_results.append(executed("quakes", ["earthquakes"]))
    # Generic retrieval alone must not close a compound request.
    assert _data_obligation_unmet(value)
    assert not CompletionEvaluator.data_checks(value)["required_data_retrieved"]
    value.tool_results.append(executed("weather", ["weather"]))
    assert not _data_obligation_unmet(value)
    assert CompletionEvaluator.data_checks(value)["required_data_retrieved"]
    # One source whose manifest covers both components also satisfies them.
    value.tool_results = [executed("combined", ["weather", "earthquakes"])]
    assert not _data_obligation_unmet(value)


###############################################################################
def test_only_idempotent_tool_results_are_replayable() -> None:
    loop = make_loop(_ScriptedProvider([]), None)  # type: ignore[arg-type]
    assert loop._result_cacheable("discover_geospatial_capabilities")
    assert not loop._result_cacheable("execute_geospatial_capability")
    assert not loop._result_cacheable("unregistered_tool")


###############################################################################
def test_raster_descriptor_does_not_close_numeric_retrieval() -> None:
    value = state()
    value.tool_results.append(ToolResult(call_id="raster", tool_name="execute_geospatial_capability", status="success", summary="descriptor",
                                      metadata=ToolExecutionMetadata(duration_ms=0, capability_id="imagery", result_type="raster")))
    assert _data_obligation_unmet(value)


###############################################################################
@pytest.mark.asyncio
async def test_transform_on_raster_imagery_fails_fast_and_ends_a_request_for_values() -> None:
    repo = MemoryEvidence()
    raster = repo.create(kind="raster_descriptor", media_type="application/json", status="available",
                         payload={"layer": "fires"}, summary={}, provenance={"provider_id": "gibs"})
    operations = [{"op": "limit", "value": 1}]

    values = state()  # a ranking route: raster imagery never satisfies it
    values.evidence_refs = [raster.evidence_id]
    result = await EvidenceToolHandler(repository=repo).transform(
        TransformEvidenceInput(evidence_refs=values.evidence_refs, operations=operations), values)
    assert result.error is not None and result.error.recovery == "terminal"
    stop = AgentLoop._evaluate_stop(values, values.route, [result], max_consecutive_tool_failures=3,
                                    max_validation_corrections=3, max_discovery_attempts=3)
    assert stop == ("insufficient_evidence", result.error.message)
    assert "imagery" in result.error.message and "Not completed" not in result.error.message

    display = state()
    display.route.analysis = None  # imagery answers a plain display request
    display.evidence_refs = [raster.evidence_id]
    shown = await EvidenceToolHandler(repository=repo).transform(
        TransformEvidenceInput(evidence_refs=display.evidence_refs, operations=operations), display)
    assert shown.error is not None and shown.error.recovery == "choose_alternate_tool"
    assert "apply_map_plan" in shown.error.message
    assert AgentLoop._evaluate_stop(display, display.route, [shown], max_consecutive_tool_failures=3,
                                    max_validation_corrections=3, max_discovery_attempts=3) is None


###############################################################################
@pytest.mark.asyncio
async def test_spatial_join_persists_traceable_polygon_evidence() -> None:
    repo = MemoryEvidence()
    ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    regions = repo.create(kind="vector", media_type="application/json", status="available",
                          payload={"features": [{"type": "Feature", "properties": {"name": "zone"},
                                                 "geometry": {"type": "Polygon", "coordinates": [ring]}}]},
                          summary={}, provenance={"provider_id": "geoboundaries"})
    quakes = repo.create(kind="vector", media_type="application/json", status="available",
                         payload={"features": [{"latitude": 0.5, "longitude": 0.5, "magnitude": 3}]},
                         summary={}, provenance={"provider_id": "usgs"})
    value = state("World")
    value.route.analysis = None
    value.evidence_refs = [regions.evidence_id, quakes.evidence_id]
    join = {"op": "spatial_join", "target_ref": regions.evidence_id, "join_ref": quakes.evidence_id}
    result = await EvidenceToolHandler(repository=repo).transform(
        TransformEvidenceInput(evidence_refs=value.evidence_refs, operations=[join, {"op": "area"}]), value)
    assert result.status == "success" and result.data["preview"][0]["properties"]["joined_count"] == 1
    assert "geometry" not in result.data["preview"][0]
    derived = repo.records[result.evidence_refs[0]][0]
    assert derived.provenance["geometry_ops"] == ["spatial_join", "area"]
    assert derived.provenance["footprint_basis"] == "polygon"
    assert derived.summary["map_eligibility"] == "renderable" and derived.summary["bbox"] == [0, 0, 1, 1]

    same = {**join, "join_ref": regions.evidence_id}
    rejected = await EvidenceToolHandler(repository=repo).transform(
        TransformEvidenceInput(evidence_refs=value.evidence_refs, operations=[same]), value)
    assert rejected.error is not None and rejected.error.code == "invalid_transform"


###############################################################################
def test_unresolvable_extra_place_asks_only_while_a_route_target_is_unresolved() -> None:
    value = state("Italy")
    resolved = ToolResult(call_id="italy", tool_name="resolve_geospatial_location", status="success",
                          summary="Resolved Italy.", metadata=ToolExecutionMetadata(duration_ms=1))
    extra = ToolResult(
        call_id="regions", tool_name="resolve_geospatial_location", status="failed",
        summary="I could not safely resolve Italian regions.",
        error=ToolExecutionError(error_type="state_conflict", code="clarification_required",
                                 message="I could not safely resolve Italian regions.", retryable=False,
                                 recovery="request_user_input"),
        metadata=ToolExecutionMetadata(duration_ms=1))

    def stop() -> tuple[str, str] | None:
        return AgentLoop._evaluate_stop(value, value.route, [resolved, extra], max_consecutive_tool_failures=3,
                                        max_validation_corrections=3, max_discovery_attempts=3)

    assert stop() == ("clarification_required", "I could not safely resolve Italian regions.")
    value.location_refs["Italy"] = ResolvedLocation(label="Italy", country="Italy", latitude=42.6, longitude=12.7,
                                                    location_type="country")
    assert stop() is None


###############################################################################
def test_checkpoint_preserves_typed_intent_but_redacts_unstructured_analysis() -> None:
    from server.repositories.agent_runs import redact_trace_payload
    intent = {"kind": "rank", "metric": "rain", "order": "descending", "top_k": 5}
    payload = {"route": {"location_mode": "search_area", "analysis": intent},
               "analysis": "private reasoning", "provider": {"analysis": "private reasoning"}}
    safe = redact_trace_payload(payload)
    assert safe["route"]["analysis"] == intent
    assert "analysis" not in safe and "analysis" not in safe["provider"]
    assert "analysis" not in redact_trace_payload({"location_mode": "target", "analysis": {**intent, "thoughts": "private"}})


###############################################################################
def test_numeric_sort_spatial_epoch_statistics_and_grid() -> None:
    records = [{"latitude": 45, "longitude": 8, "value": 9, "time": 1767225600000},
               {"latitude": 45.1, "longitude": 8.1, "value": 100, "time": 1767229200000},
               {"value": None}]
    ranked, error = _apply_operations(records, [{"op": "sort", "field": "value", "descending": True}])
    assert error is None and [item["value"] for item in ranked] == [100, 9, None]
    filtered, _ = _apply_operations(records, [{"op": "spatial_filter", "center": [8, 45], "radius_km": 20}])
    assert len(filtered) == 2
    temporal, _ = _apply_operations(records, [{"op": "temporal_filter", "field": "time", "start": "2026-01-01T00:30:00Z"}])
    assert len(temporal) == 1 and temporal[0]["value"] == 100
    cells, _ = _apply_operations(records, [{"op": "grid_aggregate", "cell_size_deg": 2, "value_field": "value"}])
    assert cells[0]["count"] == 2 and cells[0]["sum"] == 109
    statistics = _inspect_payload({"features": records}, view="statistics", fields=[], cursor=None, limit=5)["statistics"]["value"]
    assert statistics["mean"] == 54.5 and statistics["argmax"]["value"] == 100


###############################################################################
@pytest.mark.asyncio
async def test_derived_bbox_preview_and_provenance() -> None:
    repo = MemoryEvidence()
    parent = repo.create(kind="vector", media_type="application/json", status="available",
                         payload={"features": [{"latitude": 45, "longitude": 8, "value": 100}]},
                         summary={"coverage": {"type": "grid_sample", "point_count": 100}},
                         provenance={"provider_id": "openmeteo", "units": {"value": "mm"}, "value_kind": "model_estimate"})
    value = state()
    value.evidence_refs = [parent.evidence_id]
    result = await EvidenceToolHandler(repository=repo).transform(TransformEvidenceInput(
        evidence_refs=value.evidence_refs, operations=[{"op": "limit", "value": 1}]), value)
    derived, payload = repo.get_payload(result.evidence_refs[0])
    assert derived.summary["bbox"] == [8, 45, 8, 45]
    assert derived.provenance["value_kind"] == "model_estimate"
    assert "features" in json.loads(payload) and "records" not in json.loads(payload)
    assert result.data["preview"][0]["value"] == 100


###############################################################################
@pytest.mark.asyncio
async def test_transform_answers_nearest_and_country_questions_deterministically() -> None:
    repo = MemoryEvidence()
    features = [
        {"latitude": 48.8566, "longitude": 2.3522, "name": "Paris"},
        {"latitude": 45.4642, "longitude": 9.19, "name": "Milan"},
        {"latitude": 41.8902, "longitude": 12.4922, "name": "Colosseum"},
    ]
    parent = repo.create(kind="vector", media_type="application/json", status="available",
                         payload={"features": features}, summary={}, provenance={"provider_id": "test"})
    value = state()
    value.evidence_refs = [parent.evidence_id]
    value.location_refs["rome"] = ResolvedLocation(label="Rome, Italy", latitude=41.9028, longitude=12.4964)

    result = await EvidenceToolHandler(repository=repo).transform(TransformEvidenceInput(
        evidence_refs=value.evidence_refs,
        operations=[{"op": "distance_from", "location_ref": "rome"}, {"op": "country_tag"},
                    {"op": "sort", "field": "distance_km"}, {"op": "limit", "value": 2}]), value)

    nearest = result.data["preview"]
    assert [item["name"] for item in nearest] == ["Colosseum", "Milan"]
    assert nearest[0]["distance_km"] < 2
    assert 470 < nearest[1]["distance_km"] < 485
    assert [item["country_iso2"] for item in nearest] == ["IT", "IT"]

###############################################################################
@pytest.mark.asyncio
async def test_measurement_tool_computes_geodesic_distance_and_country() -> None:
    from server.services.agent.tool_definitions import MeasureGeospatialInput
    from server.services.agent.tool_handlers.measure import MeasureToolHandler

    value = state()
    value.location_refs.update({
        "paris": ResolvedLocation(label="Paris, France", latitude=48.8566, longitude=2.3522),
        "berlin": ResolvedLocation(label="Berlin, Germany", latitude=52.52, longitude=13.405),
        "atlantic": ResolvedLocation(label="40, -40", latitude=40.0, longitude=-40.0),
    })
    handler = MeasureToolHandler()

    distance = await handler.measure(
        MeasureGeospatialInput(operation="distance", location_refs=["paris", "berlin"]), value)
    pair = distance.data["measurements"][0]
    assert 875 < pair["distance_km"] < 881
    assert pair["bearing_compass"] == "NE"
    assert "Paris, France to Berlin, Germany" in distance.summary

    countries = await handler.measure(
        MeasureGeospatialInput(operation="country_of", location_refs=["paris", "atlantic"]), value)
    assert [item["country_iso2"] for item in countries.data["measurements"]] == ["FR", None]

    unknown = await handler.measure(
        MeasureGeospatialInput(operation="distance", location_refs=["paris", "madrid"]), value)
    assert unknown.status == "failed" and unknown.error.recovery == "correct_arguments"

###############################################################################
@pytest.mark.asyncio
async def test_transform_labels_leading_coordinate_points_with_nearest_place() -> None:
    repo = MemoryEvidence()
    features = [{"latitude": 40 + index, "longitude": 8, "name": f"{40 + index}, 8", "label_kind": "coordinates",
                 "value": 100 - index} for index in range(12)]
    parent = repo.create(kind="vector", media_type="application/json", status="available",
                         payload={"features": features}, summary={}, provenance={"provider_id": "openmeteo"})
    value = state()
    value.evidence_refs = [parent.evidence_id]
    calls: list[tuple[float, float]] = []
    async def labeler(latitude: float, longitude: float) -> str | None:
        calls.append((latitude, longitude))
        return None if latitude == 41 else f"Place {latitude:g}, Country"
    result = await EvidenceToolHandler(repository=repo, place_labeler=labeler).transform(TransformEvidenceInput(
        evidence_refs=value.evidence_refs, operations=[{"op": "sort", "field": "value", "descending": True}]), value)
    _, payload = repo.get_payload(result.evidence_refs[0])
    records = json.loads(payload)["features"]
    assert calls == [(40 + index, 8) for index in range(10)]
    assert records[0]["place_label"] == "Place 40, Country" and records[0]["label_kind"] == "nearest_reverse_geocoded"
    # A failed lookup and points past the cap stay coordinate-only.
    assert "place_label" not in records[1] and records[1]["label_kind"] == "coordinates"
    assert "place_label" not in records[10]
    assert result.data["place_labelled_count"] == 9


###############################################################################
@pytest.mark.asyncio
async def test_invalid_value_field_is_correctable_and_europe_needs_no_geocoder():
    from server.domain.agent.evidence import AgentEvidenceEnvelope
    from server.domain.agent.map_plan import AddEvidenceLayerAction, SetBasemapAction
    from server.services.geospatial.map_session_builder import MapSessionBuilder, MapPlanBuildError
    from server.services.geospatial.capability_registry import CapabilityRegistry
    builder = MapSessionBuilder(capability_registry=CapabilityRegistry())
    location = find_macro_region("Europe")
    evidence = AgentEvidenceEnvelope(ok=True, status="available", evidence_ref="derived",
        map_eligibility="renderable", summary={"bbox": [8, 45, 9, 46]},
        payload={"features": [{"latitude": 45, "longitude": 8, "value": 3}]})
    actions = [SetBasemapAction(action="set_basemap", capability_id="osm_default"),
        AddEvidenceLayerAction(action="add_evidence_layer", capability_id="openmeteo_weather_forecast", evidence_ref="derived",
            value_encoding={"mode": "graduated", "field": "missing"})]
    with pytest.raises(MapPlanBuildError) as error:
        await builder.build(location=location, evidence=[evidence], actions=actions, active_session=None)
    assert error.value.code == "invalid_value_field"


###############################################################################
def test_discovery_prompt_requires_disclosure_and_forbids_overclaiming():
    from server.prompts.agent import build_native_agent_system_prompt
    prompt = build_native_agent_system_prompt()
    for term in ["grid_aggregate", "fit_evidence", "value_encoding", "observed vs modelled", "partial or excluded", "verified maximum", "evidence does not contain", "near <place_label>", "completeness_note"]:
        assert term in prompt

# --- test_native_harness_trajectories.py ---




###############################################################################
class _Provider:

    # -------------------------------------------------------------------------
    def __init__(self, results: list[LLMResult]) -> None:
        self.results = deque(results)
        self.requests: list[Any] = []

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **_kwargs: Any) -> LLMResult:
        self.requests.append(request)
        return self.results.popleft()

###############################################################################
class _BlockingProvider:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = False

    # -------------------------------------------------------------------------
    async def achat(self, _request: Any, **_kwargs: Any) -> LLMResult:
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("The cancelled provider call unexpectedly returned.")

###############################################################################
class _Factory:

    # -------------------------------------------------------------------------
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, _provider: str) -> _Provider:
        return self.provider

###############################################################################
class _Runtime:

    # -------------------------------------------------------------------------
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, _capability_id: str) -> bool:
        return True

###############################################################################
class _Catalog:

    # -------------------------------------------------------------------------
    def servable_queries(self, queries: Any) -> list[str]:
        return list(queries)

    # -------------------------------------------------------------------------
    def __init__(self, *, empty_first: bool) -> None:
        self.empty_first = empty_first
        self.shortlist_calls = 0
        self.capabilities = {
            "primary-source": {
                "id": "primary-source",
                "name": "Primary source",
                "description": "Primary geospatial source.",
                "provider": "primary",
                "capabilityKind": "vector-overlay",
            },
            "alternate-source": {
                "id": "alternate-source",
                "name": "Alternate source",
                "description": "Equivalent alternate geospatial source.",
                "provider": "alternate",
                "capabilityKind": "vector-overlay",
            },
        }

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict[str, object] | None:
        return self.capabilities.get(capability_id)

    # -------------------------------------------------------------------------
    def shortlist(self, **_kwargs: Any) -> list[dict[str, object]]:
        self.shortlist_calls += 1
        if self.empty_first and self.shortlist_calls == 1:
            return []
        return list(self.capabilities.values())

    # -------------------------------------------------------------------------
    def execution_contract(self, _capability_id: str) -> dict[str, object]:
        return {
            "supported_operations": ["show"],
            "supported_scope_kinds": ["point", "bbox"],
        }

###############################################################################
def _route_call(*, complex_route: bool = False) -> LLMResult:
    arguments: dict[str, Any] = {
        "primary_domain": "data_retrieval",
        "task_mode": "execute",
        "presentation": "text",
        "location_mode": "none",
        "capability_queries": ["obscure geospatial data"],
    }
    if complex_route:
        arguments["secondary_domains"] = ["spatial_analysis"]
    return LLMResult(
        content="",
        tool_calls=[
            LLMToolCall(
                id="route-1",
                name="route_request",
                arguments=arguments,
            )
        ],
    )

###############################################################################
def _state() -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.RECEIVE_REQUEST,
        user_message="Find obscure geospatial data.",
    )

###############################################################################
def _registration(
    *,
    name: str,
    input_model: type[BaseModel],
    handler: Any,
    prerequisites: frozenset[str],
    phase: AgentPhase = AgentPhase.BUILD_TOOL_CONTEXT,
    visibility: str = "model",
) -> RegisteredTool:
    return RegisteredTool(
        definition=LLMToolDefinition(
            name=name,
            description=f"Test {name}.",
            parameters_json_schema=input_model.model_json_schema(),
        ),
        input_model=input_model,
        handler=handler,
        domains=frozenset({CapabilityDomain.MIXED}),
        phases=frozenset({phase}),
        visibility=visibility,  # type: ignore[arg-type]
        prerequisites=prerequisites,
        timeout_key="tool_execution_seconds",
        idempotent=name.startswith("discover_"),
        result_normalizer=lambda value, call_id: value.model_copy(
            update={"call_id": call_id}
        ),
    )

###############################################################################
def _loop(
    provider: _Provider,
    *,
    catalog: _Catalog,
    execute_handler: Any,
) -> AgentLoop:
    runtime = _Runtime()
    registry = ToolRegistry(runtime_registry=runtime)  # type: ignore[arg-type]
    catalog_handler = CatalogToolHandler(
        capability_registry=catalog,  # type: ignore[arg-type]
        runtime_registry=runtime,  # type: ignore[arg-type]
    )
    registry.register(
        _registration(
            name="route_request",
            input_model=RouteRequestInput,
            handler=execute_handler,
            prerequisites=frozenset(),
            phase=AgentPhase.ROUTE_REQUEST,
            visibility="internal",
        )
    )
    registry.register(
        _registration(
            name="discover_geospatial_capabilities",
            input_model=CapabilityDiscoveryInput,
            handler=catalog_handler.discover,
            prerequisites=frozenset({"route", "capability_shortlist_missing"}),
        )
    )
    registry.register(
        _registration(
            name="execute_geospatial_capability",
            input_model=ExecuteCapabilityInput,
            handler=execute_handler,
            prerequisites=frozenset({"route", "capability_shortlist"}),
        )
    )
    return AgentLoop(
        provider_factory=_Factory(provider),  # type: ignore[arg-type]
        capability_router=CapabilityRouter(
            capability_registry=catalog,  # type: ignore[arg-type]
            runtime_registry=runtime,  # type: ignore[arg-type]
        ),
        tool_registry=registry,
        tool_executor=ToolExecutor(
            tool_registry=registry,
            policy_engine=PolicyEngine(
                capability_registry=catalog,  # type: ignore[arg-type]
                runtime_registry=runtime,  # type: ignore[arg-type]
            ),
        ),
    )

###############################################################################
def _success(call_id: str, capability_id: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        tool_name="execute_geospatial_capability",
        status="success",
        summary=f"Retrieved data from {capability_id}.",
        data={"features": [{"id": "feature-1"}]},
        evidence_refs=[f"evidence:{capability_id}"],
        metadata=ToolExecutionMetadata(
            capability_id=capability_id,
            provider_id=capability_id,
            duration_ms=0,
            result_type="features",
            result_status="success",
        ),
    )

###############################################################################
@pytest.mark.asyncio
async def test_empty_shortlist_exposes_discovery_and_observes_descriptors() -> None:
    async def execute(_arguments: ExecuteCapabilityInput, _state: AgentRunState) -> ToolResult:
        return _success("handler-call", "primary-source")

    provider = _Provider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="discover-1",
                        name="discover_geospatial_capabilities",
                        arguments={"query": "obscure geospatial data"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-1",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(content="The discovered source answered the request."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=True),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=6,
            max_tool_calls=6,
            max_state_transitions=32,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert outcome.state.capability_ids == ["primary-source", "alternate-source"]
    assert any(
        "primary-source" in json.dumps(request.messages)
        for request in provider.requests[1:]
    )

###############################################################################
@pytest.mark.asyncio
async def test_replan_reopens_discovery_and_selects_an_alternate_source() -> None:
    calls: list[str] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(arguments.capability_id)
        if arguments.capability_id == "primary-source":
            return ToolResult(
                call_id="handler-call",
                tool_name="execute_geospatial_capability",
                status="failed",
                summary="The primary provider timed out.",
                error=ToolExecutionError(
                    error_type="provider_unavailable",
                    code="provider_timeout",
                    message="The primary provider timed out.",
                    retryable=False,
                    recovery="replan",
                ),
                metadata=ToolExecutionMetadata(
                    capability_id="primary-source",
                    provider_id="primary",
                    duration_ms=0,
                ),
            )
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(complex_route=True),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-primary",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="discover-alternate",
                        name="discover_geospatial_capabilities",
                        arguments={},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-alternate",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "alternate-source"},
                    )
                ],
            ),
            LLMResult(content="The alternate source answered the request."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=8,
            max_tool_calls=8,
            max_state_transitions=48,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert calls == ["primary-source", "alternate-source"]
    assert outcome.state.excluded_capability_ids == ["primary-source"]
    assert outcome.state.capability_ids == ["alternate-source"]
    assert any(
        "provider_timeout" in json.dumps(request.messages)
        for request in provider.requests
    )

###############################################################################
@pytest.mark.asyncio
async def test_valid_empty_result_allows_a_materially_different_alternate_query() -> None:
    calls: list[str] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(arguments.capability_id)
        if arguments.capability_id == "primary-source":
            return ToolResult(
                call_id="handler-call",
                tool_name="execute_geospatial_capability",
                status="valid_empty",
                semantic_outcome="not_found",
                summary="The primary source returned no matching features.",
                data={"features": []},
                metadata=ToolExecutionMetadata(
                    capability_id="primary-source",
                    provider_id="primary",
                    duration_ms=0,
                    result_type="features",
                    result_status="valid_empty",
                ),
            )
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(complex_route=True),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-empty",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="discover-alternate",
                        name="discover_geospatial_capabilities",
                        arguments={"query": "widened hospitals"},
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="execute-alternate",
                        name="execute_geospatial_capability",
                        arguments={
                            "capability_id": "alternate-source",
                            "filters": {"widened": True},
                        },
                    )
                ],
            ),
            LLMResult(content="The alternate query found the requested data."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=8,
            max_tool_calls=8,
            max_state_transitions=48,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert calls == ["primary-source", "alternate-source"]
    assert [result.status for result in outcome.tool_results] == [
        "valid_empty",
        "success",
        "success",
    ]

###############################################################################
@pytest.mark.asyncio
async def test_malformed_tool_call_is_corrected_in_the_same_native_run() -> None:
    calls: list[str] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(arguments.capability_id)
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="malformed-call",
                        name="execute_geospatial_capability",
                        arguments=None,
                        parse_error="invalid_json",
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="corrected-call",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
            LLMResult(content="The corrected call completed the request."),
        ]
    )
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=_state(),
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_model_calls=8,
            max_tool_calls=8,
            max_state_transitions=48,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    assert calls == ["primary-source"]
    # The successful corrected call resets the consecutive-invalid guard.
    assert outcome.state.validation_corrections == 0
    assert [result.status for result in outcome.tool_results] == [
        "failed",
        "success",
    ]

###############################################################################
@pytest.mark.asyncio
async def test_successful_native_data_stops_before_redundant_model_turns() -> None:
    calls: list[int] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(int(arguments.filters["step"]))
        return _success("handler-call", "primary-source")

    model_results = [_route_call(complex_route=True)]
    model_results.extend(
        LLMResult(
            content="",
            tool_calls=[
                LLMToolCall(
                    id=f"execute-{step}",
                    name="execute_geospatial_capability",
                    arguments={
                        "capability_id": "primary-source",
                        "filters": {"step": step},
                    },
                )
            ],
        )
        for step in range(8)
    )
    model_results.append(LLMResult(content="The bounded native trajectory completed."))
    provider = _Provider(model_results)
    state = _state()
    state.context_hydrated = True
    outcome = await _loop(
        provider,
        catalog=_Catalog(empty_first=False),
        execute_handler=execute,
    ).run(
        AgentLoopRequest(
            provider="fake",
            model="fake-model",
            state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            max_iterations=12,
            max_model_calls=10,
            max_tool_calls=12,
            max_state_transitions=128,
        )
    )

    assert outcome.stopped_reason == "goal_satisfied"
    # A successful provider result satisfies the data obligation.  The loop
    # must reserve one finalizer turn and stop instead of replaying the model's
    # redundant follow-up calls until the action budget is exhausted.
    assert outcome.model_calls == 3
    assert outcome.state.tool_calls == 1
    assert calls == [0]
    assert len(provider.requests) == 3
    assert any(
        "CANONICAL_NATIVE_CONTEXT" in str(message.get("content", ""))
        for message in provider.requests[-1].messages
    )

###############################################################################
@pytest.mark.asyncio
async def test_cancellation_during_model_call_returns_a_cancelled_outcome() -> None:
    provider = _BlockingProvider()

    async def execute(_arguments: ExecuteCapabilityInput, _state: AgentRunState) -> ToolResult:
        return _success("handler-call", "primary-source")

    task = asyncio.create_task(
        _loop(
            provider,  # type: ignore[arg-type]
            catalog=_Catalog(empty_first=False),
            execute_handler=execute,
        ).run(
            AgentLoopRequest(
                provider="fake",
                model="fake-model",
                state=_state(),
                budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            )
        )
    )
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    task.cancel()
    outcome = await task

    assert provider.cancelled is True
    assert outcome.stopped_reason == "cancelled"
    assert outcome.state.termination_reason == "cancelled"
    assert outcome.state.tool_calls == 0

###############################################################################
@pytest.mark.asyncio
async def test_cancellation_during_tool_call_does_not_apply_a_partial_result() -> None:
    provider = _Provider(
        [
            _route_call(),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="blocked-tool",
                        name="execute_geospatial_capability",
                        arguments={"capability_id": "primary-source"},
                    )
                ],
            ),
        ]
    )
    entered = asyncio.Event()

    async def execute(
        _arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        entered.set()
        await asyncio.Event().wait()
        return _success("handler-call", "primary-source")

    task = asyncio.create_task(
        _loop(
            provider,
            catalog=_Catalog(empty_first=False),
            execute_handler=execute,
        ).run(
            AgentLoopRequest(
                provider="fake",
                model="fake-model",
                state=_state(),
                budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
            )
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    outcome = await task

    assert outcome.stopped_reason == "cancelled"
    assert outcome.state.termination_reason == "cancelled"
    assert outcome.state.tool_calls == 1
    assert outcome.state.tool_results == []

###############################################################################
def _execute_call(call_id: str, capability_id: str, **arguments: Any) -> LLMToolCall:
    return LLMToolCall(
        id=call_id,
        name="execute_geospatial_capability",
        arguments={"capability_id": capability_id, "arguments": arguments},
    )

###############################################################################
def _request(**limits: Any) -> AgentLoopRequest:
    return AgentLoopRequest(
        provider="fake",
        model="fake-model",
        state=_state(),
        budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        max_model_calls=8,
        max_tool_calls=8,
        max_state_transitions=64,
        **limits,
    )

###############################################################################
@pytest.mark.asyncio
async def test_excluded_capability_cannot_be_executed_again_in_the_same_run() -> None:
    calls: list[str] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        calls.append(arguments.capability_id)
        return ToolResult(
            call_id="handler-call",
            tool_name="execute_geospatial_capability",
            status="failed",
            summary="The primary provider timed out.",
            error=ToolExecutionError(
                error_type="provider_unavailable",
                code="provider_timeout",
                message="The primary provider timed out.",
                retryable=False,
                recovery="replan",
            ),
            metadata=ToolExecutionMetadata(
                capability_id="primary-source", provider_id="primary", duration_ms=0
            ),
        )

    provider = _Provider(
        [
            _route_call(complex_route=True),
            LLMResult(content="", tool_calls=[_execute_call("first", "primary-source")]),
            LLMResult(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="discover", name="discover_geospatial_capabilities", arguments={}
                    )
                ],
            ),
            # A materially different argument set must not bypass exclusion.
            LLMResult(
                content="",
                tool_calls=[_execute_call("again", "primary-source", query="other")],
            ),
            LLMResult(content="No source could answer the request."),
        ]
    )
    outcome = await _loop(
        provider, catalog=_Catalog(empty_first=False), execute_handler=execute
    ).run(_request())

    assert calls == ["primary-source"]
    rejected = next(item for item in outcome.state.tool_results if item.call_id == "again")
    assert rejected.error is not None
    assert rejected.error.error_type == "policy_rejection"
    assert rejected.error.recovery == "choose_alternate_tool"

###############################################################################
@pytest.mark.asyncio
async def test_truncated_tool_batch_answers_every_model_call_id() -> None:
    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(complex_route=True),
            LLMResult(
                content="",
                tool_calls=[
                    _execute_call(f"batch-{index}", "primary-source", index=index)
                    for index in range(3)
                ],
            ),
            LLMResult(content="The data was retrieved."),
            LLMResult(content="The data was retrieved."),
        ]
    )
    outcome = await _loop(
        provider, catalog=_Catalog(empty_first=False), execute_handler=execute
    ).run(_request(max_parallel_tool_calls=2))

    assert outcome.state.tool_calls == 2
    follow_up = provider.requests[2].messages
    requested = [
        call["id"]
        for message in follow_up
        if message.get("role") == "assistant"
        for call in message.get("tool_calls") or []
    ]
    answered = {
        message["tool_call_id"]: json.loads(message["content"])
        for message in follow_up
        if message.get("role") == "tool"
    }
    assert requested == ["batch-0", "batch-1", "batch-2"]
    assert set(answered) == set(requested)
    assert "tool_call_not_executed" in json.dumps(answered["batch-2"])
    assert "tool_call_not_executed" not in json.dumps(answered["batch-0"])

###############################################################################
@pytest.mark.asyncio
async def test_cancellation_in_parallel_batch_stops_sibling_tool_handlers() -> None:
    run_signal: dict[str, str | None] = {"value": None}
    completed: list[int] = []

    async def execute(
        arguments: ExecuteCapabilityInput, _state: AgentRunState
    ) -> ToolResult:
        index = int(arguments.arguments["index"])
        await asyncio.sleep(0.01 if index == 0 else 0.2)
        if index == 0:
            run_signal["value"] = "cancelled"
        completed.append(index)
        return _success("handler-call", arguments.capability_id)

    provider = _Provider(
        [
            _route_call(complex_route=True),
            LLMResult(
                content="",
                tool_calls=[
                    _execute_call(f"parallel-{index}", "primary-source", index=index)
                    for index in range(2)
                ],
            ),
        ]
    )
    outcome = await _loop(
        provider, catalog=_Catalog(empty_first=False), execute_handler=execute
    ).run(_request(run_state_check=lambda: run_signal["value"]))
    await asyncio.sleep(0.3)

    assert outcome.stopped_reason == "cancelled"
    assert completed == [0]


###############################################################################
def test_ranking_on_a_field_the_evidence_lacks_fails_instead_of_succeeding_silently() -> None:
    records = [{"latitude": 46, "longitude": 8, "precipitation_sum_mm": 3}, {"latitude": 47, "longitude": 9, "precipitation_sum_mm": 1}]
    _, error = _apply_operations(records, [{"op": "sort", "field": "cloud_cover_mean"}])
    assert error is not None and "cloud_cover_mean" in error and "precipitation_sum_mm" in error


###############################################################################
def test_country_ranking_excludes_records_in_neighbouring_countries() -> None:
    from server.services.agent.tool_handlers.evidence import _within_requested_country
    state = AgentRunState(request_id="r", conversation_id="c", phase=AgentPhase.RECEIVE_REQUEST, user_message="rank")
    state.location_refs["switzerland"] = ResolvedLocation(label="Switzerland", latitude=46.8, longitude=8.2, location_type="country")
    state.goal = AgentGoal(goal="rank", task_mode="execute", presentation="text", operation="rank", location_mode="target", target_ids=["Switzerland"])
    records = [{"latitude": 46.8, "longitude": 8.2, "id": "ch"}, {"latitude": 45.5, "longitude": 9.2, "id": "milan"}, {"latitude": 40.5, "longitude": 3.0, "id": "sea"}]
    kept, excluded = _within_requested_country(records, state)
    assert [item["id"] for item in kept] == ["ch", "sea"] and excluded == 1


###############################################################################
def test_a_raster_layer_never_satisfies_a_requested_aggregate() -> None:
    state = AgentRunState(request_id="r", conversation_id="c", phase=AgentPhase.RECEIVE_REQUEST, user_message="max temperature")
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL, task_mode="execute", presentation="text", location_mode="none",
        temporal_scope=AgentTemporalScope(mode="historical", aggregation="maximum"),
    )
    state.completion_contract = CompletionContract(operation="show", evidence_required=True)
    state.tool_results = [ToolResult(
        call_id="lst", tool_name="execute_geospatial_capability", status="success", summary="raster", evidence_refs=["e1"],
        metadata=ToolExecutionMetadata(duration_ms=0, capability_id="MODIS_Terra_Land_Surface_Temp_Day", result_type="raster"),
    )]
    assert CompletionEvaluator.data_checks(state)["required_data_retrieved"] is False
    state.route = state.route.model_copy(update={"temporal_scope": AgentTemporalScope(mode="historical")})
    assert CompletionEvaluator.data_checks(state)["required_data_retrieved"] is True


###############################################################################
def test_a_requested_variable_the_source_lacks_is_reported_as_unmet() -> None:
    from server.services.agent.capability_execution import _unmet_requested_attributes
    response = ProviderResponse(
        capability_id="openmeteo_weather_forecast", provider_id="openmeteo", result_type="features",
        payload={"features": [{"cloud_cover_mean": 20, "temperature_2m_max_c": 9}]}, coverage={"type": "grid_sample"},
    )
    request = ExecuteCapabilityInput(
        capability_id="openmeteo_weather_forecast",
        arguments={"requested_attributes": ["cloud cover", "visibility"]},
    )
    assert _unmet_requested_attributes(request, response, {}) == ["visibility"]


###############################################################################
def test_fallback_answers_carry_the_values_and_sources_the_question_asked_for() -> None:
    forecast = ToolResult(
        call_id="f", tool_name="execute_geospatial_capability", status="success", summary="Forecast returned.",
        data={"hourly_forecast": [{"time": "t0", "cloud_cover": 10}, {"time": "t1", "cloud_cover": 90}], "units": {"cloud_cover": "%"}},
        metadata=ToolExecutionMetadata(duration_ms=0),
    )
    assert "cloud cover 10 to 90 %" in AgentLoop._forecast_values(forecast)

    state = AgentRunState(request_id="r", conversation_id="c", phase=AgentPhase.RECEIVE_REQUEST, user_message="what data?")
    state.goal = AgentGoal(goal="what data?", task_mode="execute", presentation="text", operation="discover_available_map_data", location_mode="target")
    state.tool_results = [ToolResult(
        call_id="d", tool_name="discover_geospatial_capabilities", status="success", summary="Found 1 eligible capabilities.",
        data={"capabilities": [{"id": "wikidata_place_facts", "name": "Wikidata Place Facts", "summary": "Population of a place."}]},
        metadata=ToolExecutionMetadata(duration_ms=0),
    )]
    assert "Wikidata Place Facts: Population of a place." in AgentLoop._evidence_findings(state)


###############################################################################
def test_requested_forecast_variables_survive_the_model_observation_projection() -> None:
    from server.domain.agent.tool_result import _project_result_data
    data = {"kind": "weather_forecast", "hourly_forecast": [{"time": "t0", "temperature_2m": 5, "cloud_cover": 40}], "requested_fields": ["cloud_cover"]}
    projected, _ = _project_result_data("execute_geospatial_capability", data, max_chars=4000)
    assert isinstance(projected, dict) and projected["hourly_forecast"]["fields"][-1] == "cloud_cover" and projected["hourly_forecast"]["rows"][0][-1] == 40


###############################################################################
def test_imagery_only_answer_names_the_missing_values() -> None:
    from server.services.agent.completion import imagery_only_note
    state = AgentRunState(request_id="r", conversation_id="c", phase=AgentPhase.RECEIVE_REQUEST, user_message="max temperature")
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL, task_mode="execute", presentation="text", location_mode="none",
        capability_queries=["temperature"], temporal_scope=AgentTemporalScope(mode="historical", aggregation="maximum"),
    )
    state.tool_results = [ToolResult(
        call_id="lst", tool_name="execute_geospatial_capability", status="success", summary="raster",
        metadata=ToolExecutionMetadata(duration_ms=0, result_type="raster"),
    )]
    assert "no numeric values" in imagery_only_note(state) and "maximum temperature" in imagery_only_note(state)

# --- cross-turn task ledger ---


###############################################################################
QUAKE_WEEK = {"mode": "historical", "start_time_iso": "2026-10-30T00:00:00Z", "end_time_iso": "2026-11-06T00:00:00Z"}
QUAKE_DAY = {"mode": "historical", "start_time_iso": "2026-11-05T00:00:00Z", "end_time_iso": "2026-11-06T00:00:00Z"}


###############################################################################
def _quake_route(window: dict[str, str], **extra: Any) -> dict[str, Any]:
    return {"primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "text",
            "location_mode": "search_area", "target_refs": ["World"], "operation": "inspect",
            "capability_queries": ["earthquake"], "explicit_capability_ids": ["usgs_earthquakes"],
            "temporal_scope": window, "filters": {"min_magnitude": 4.5}, **extra}


###############################################################################
class CityResolver:

    # -------------------------------------------------------------------------
    async def resolve_location_signals(self, signals: list[LocationSignal], *args: Any) -> ResolvedLocation:
        name = signals[0].raw_value
        latitude, longitude = {"Paris": (48.85, 2.35), "Berlin": (52.52, 13.4), "Lisbon": (38.72, -9.14)}[name]
        return ResolvedLocation(label=name, latitude=latitude, longitude=longitude, location_type="city",
                                bbox=[longitude - 0.2, latitude - 0.2, longitude + 0.2, latitude + 0.2])


###############################################################################
async def _turn(
    script: list[LLMResult], *, message: str, providers: DiscoveryProvider, evidence: MemoryEvidence,
    prior: AgentRunState | None = None, request_id: str,
) -> AgentRunState:
    """Run one turn; a follow-up starts from the prior turn's committed ledger."""

    ledger = [] if prior is None else merge_ledger(
        list(prior.prior_tasks),
        ledger_outcomes(prior, AgentLoop.completion_summary(prior), now=datetime.now(UTC)),
    )
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id=request_id, conversation_id="ledger",
        user_message=message, context_hydrated=True, prior_tasks=ledger,
        location_refs=dict(prior.location_refs) if prior else {},
        evidence_refs=list(prior.evidence_refs) if prior else [],
        active_map_session=(prior.prepared_map_session or prior.active_map_session) if prior else None,
    )
    await make_loop(_ScriptedProvider(script), providers, CityResolver(), evidence).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state, budget=AgentExecutionBudget(total_seconds=10)))
    return state


###############################################################################
class _PlaceResolver:

    # -------------------------------------------------------------------------
    async def resolve_location_signals(self, signals: list[LocationSignal], *args: Any) -> ResolvedLocation:
        label, country, kind, bbox = {
            "Tokyo": ("Tokyo, Japan", "Japan", "city", [139.0, 34.9, 140.5, 35.9]),
            "Portugal": ("Portugal", "Portugal", "country", [-9.5, 36.9, -6.2, 42.2]),
        }[signals[0].raw_value]
        return ResolvedLocation(
            label=label, country=country, latitude=(bbox[1] + bbox[3]) / 2, longitude=(bbox[0] + bbox[2]) / 2,
            location_type=kind, bbox=bbox,
        )


###############################################################################
async def _raster_map_run(
    message: str, route: dict[str, Any], place: str, capability: str, *, first_try: str | None = None,
    evidence: MemoryEvidence | None = None,
) -> tuple[AgentRunState, list[str]]:
    """Run route -> resolve -> (describe first_try) -> describe -> execute -> map with a keyless raster source."""

    placed = place.lower()
    providers = _FakeProviderRegistry()
    calls = ["resolve_geospatial_location", "describe_geospatial_capability", "execute_geospatial_capability", "apply_map_plan"]
    model = _ScriptedProvider([
        _call("route", "route_request", route),
        _call("resolve", calls[0], {"query": place, "target_id": place}),
        *([_call("describe-first", calls[1], {"capability_id": first_try})] if first_try else []),
        _call("describe", calls[1], {"capability_id": capability}),
        _call("execute", calls[2], {"capability_id": capability, "location_ref": placed, "operation": "show"}),
        _call("map", calls[3], {"expected_collection_revision": 0, "actions": [
            {"action": "set_basemap", "capability_id": "osm_default"},
            {"action": "add_evidence_layer", "capability_id": capability, "evidence_ref": "evidence-1"},
        ]}),
    ])
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="raster", conversation_id="raster", user_message=message,
        context_hydrated=True,
    )
    await make_loop(model, providers, _PlaceResolver(), evidence or MemoryEvidence()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state, budget=AgentExecutionBudget(total_seconds=10)))
    return state, [request.capability_id for _, request in providers.requests]


###############################################################################
@pytest.mark.asyncio
async def test_coverage_rejection_hands_over_to_the_covering_equivalent_and_maps_it() -> None:
    # S16: NOAA radar covers only the US; its declared equivalent shows Tokyo.
    route = {
        "primary_domain": "data_retrieval", "secondary_domains": ["map_rendering"], "task_mode": "execute",
        "presentation": "map", "location_mode": "target", "target_refs": ["Tokyo"], "operation": "show",
        "capability_queries": ["weather radar"], "explicit_capability_ids": [],
        "temporal_scope": {"mode": "current"},
    }
    state, fetched = await _raster_map_run(
        "Show the current weather radar over Tokyo.", route, "Tokyo", "rainviewer_precipitation_radar",
        first_try="noaa_radar",
    )

    rejection = next(item for item in state.tool_results if item.status == "failed")
    assert rejection.error is not None and rejection.error.recovery == "choose_alternate_tool"
    assert "RainViewer" in rejection.error.message and "only covers United States" in rejection.error.message
    assert fetched == ["rainviewer_precipitation_radar"]
    assert state.prepared_map_session is not None
    assert [item.capability_id for item in state.prepared_map_session.overlay_collection.instances] == [
        "rainviewer_precipitation_radar"
    ]
    assert [item.tool_name for item in state.tool_results if item.status == "failed"] == ["describe_geospatial_capability"]
    summary = AgentLoop.completion_summary(state)
    assert len(summary.substitutions) == 1
    rejected_name, coverage, alternative_name = summary.substitutions[0]
    sentence = f"{rejected_name} only covers {coverage}, so {alternative_name} is shown instead."
    assert "RainViewer" in alternative_name and coverage == "United States"
    assert summary.disclosure().startswith(sentence)
    assert AgentLoop._with_disclosure(state, "The map is ready.").startswith("The map is ready.\n\n" + sentence)
    stated = f"{rejected_name} is US-only; {alternative_name} is shown."
    assert sentence not in AgentLoop._with_disclosure(state, stated)


###############################################################################
@pytest.mark.asyncio
async def test_imagery_only_evidence_on_an_analysis_route_is_mapped_and_the_analysis_disclosed_unsupported() -> None:
    # S13: the only keyless fire source is raster imagery, so the hotspot
    # analysis cannot be computed; the layer is still shown, without any
    # unexposed or invalid tool call, and the answer discloses the gap.
    route = {
        "primary_domain": "data_retrieval", "secondary_domains": ["map_rendering"], "task_mode": "execute",
        "presentation": "map", "location_mode": "search_area", "target_refs": ["Portugal"], "operation": "show",
        "capability_queries": ["wildfire hotspots"], "explicit_capability_ids": [],
        "analysis": {"kind": "hotspot", "metric": "wildfire hotspot intensity", "top_k": 25},
        "temporal_scope": {"mode": "current", "granularity": "day"},
    }
    state, _ = await _raster_map_run(
        "Show me the current wildfire hotspots in Portugal on the map.", route, "Portugal",
        "MODIS_Combined_Thermal_Anomalies_Fire",
    )

    assert state.capability_ids == ["MODIS_Combined_Thermal_Anomalies_Fire"]
    assert [item.status for item in state.tool_results] == ["success"] * 4
    assert state.prepared_map_session is not None
    assert [item.capability_id for item in state.prepared_map_session.overlay_collection.instances] == [
        "MODIS_Combined_Thermal_Anomalies_Fire"
    ]
    summary = AgentLoop.completion_summary(state)
    assert {item.kind: item.status for item in summary.obligations if item.kind in {"data", "analysis"}} == {
        "data": "met", "analysis": "unsupported",
    }
    assert "Only map imagery was available" in summary.disclosure()
    assert set(AgentLoop._pending_native_requirements(state)) <= {"render_verified"}


###############################################################################
def _executions(state: AgentRunState) -> list[ToolResult]:
    return [item for item in state.tool_results if item.tool_name == "execute_geospatial_capability"]


###############################################################################
@pytest.mark.asyncio
async def test_strongest_follow_up_reuses_stored_evidence_without_a_provider_call() -> None:
    providers, evidence = DiscoveryProvider(), MemoryEvidence()
    first = await _turn([
        _call("route", "route_request", _quake_route(QUAKE_WEEK)),
        _call("execute", "execute_geospatial_capability", {"capability_id": "usgs_earthquakes"}),
        *(LLMResult(content="There were 2 earthquakes.") for _ in range(3)),
    ], message="List earthquakes of magnitude 4.5 or higher in the last 7 days worldwide.",
        providers=providers, evidence=evidence, request_id="t1")
    assert len(providers.requests) == 1

    second = await _turn([
        _call("route", "route_request", _quake_route(QUAKE_WEEK)),
        _call("execute", "execute_geospatial_capability", {"capability_id": "usgs_earthquakes"}),
        *(LLMResult(content="The strongest was M100.") for _ in range(3)),
    ], message="Which one was strongest?", providers=providers, evidence=evidence, prior=first, request_id="t2")

    assert len(providers.requests) == 1
    reused = _executions(second)[-1]
    assert reused.status == "success"
    assert reused.evidence_refs == _executions(first)[-1].evidence_refs
    assert isinstance(reused.data, dict) and reused.data["reused_evidence_ref"] == reused.evidence_refs[0]


###############################################################################
@pytest.mark.asyncio
async def test_changed_time_window_invalidates_evidence_reuse() -> None:
    providers, evidence = DiscoveryProvider(), MemoryEvidence()
    first = await _turn([
        _call("route", "route_request", _quake_route(QUAKE_WEEK)),
        _call("execute", "execute_geospatial_capability", {"capability_id": "usgs_earthquakes"}),
        *(LLMResult(content="There were 2 earthquakes.") for _ in range(3)),
    ], message="List earthquakes of magnitude 4.5 or higher in the last 7 days worldwide.",
        providers=providers, evidence=evidence, request_id="t1")

    second = await _turn([
        _call("route", "route_request", _quake_route(QUAKE_DAY)),
        _call("execute", "execute_geospatial_capability", {"capability_id": "usgs_earthquakes"}),
        *(LLMResult(content="There were 2 earthquakes today.") for _ in range(3)),
    ], message="And only the last 24 hours?", providers=providers, evidence=evidence, prior=first, request_id="t2")

    assert len(providers.requests) == 2
    assert providers.requests[1].time != providers.requests[0].time
    assert not any(item.kind == "data" for item in second.prior_tasks)
    fetched = _executions(second)[-1].data
    assert isinstance(fetched, dict) and "reused_evidence_ref" not in fetched


###############################################################################
def _city_weather_route(variable: str) -> dict[str, Any]:
    return {"primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "text",
            "location_mode": "target", "target_refs": ["Paris", "Berlin"], "operation": "compare",
            "capability_queries": [variable], "explicit_capability_ids": ["openmeteo_weather_forecast"],
            "temporal_scope": {"mode": "current"}}


###############################################################################
def _city_executions(prefix: str) -> list[LLMResult]:
    return [
        _call(f"{prefix}-{city}", "execute_geospatial_capability",
              {"capability_id": "openmeteo_weather_forecast", "location_ref": city})
        for city in ("Paris", "Berlin")
    ]


###############################################################################
@pytest.mark.asyncio
async def test_precipitation_follow_up_keeps_places_and_temperature_and_fetches_only_precipitation() -> None:
    providers, evidence = DiscoveryProvider(), MemoryEvidence()
    first = await _turn([
        _call("route", "route_request", _city_weather_route("temperature")),
        _call("resolve-paris", "resolve_geospatial_location", {"query": "Paris", "target_id": "Paris"}),
        _call("resolve-berlin", "resolve_geospatial_location", {"query": "Berlin", "target_id": "Berlin"}),
        *_city_executions("temperature"),
        *(LLMResult(content="Paris 9 C, Berlin 9 C.") for _ in range(3)),
    ], message="What are today's temperatures in Paris and Berlin?",
        providers=providers, evidence=evidence, request_id="t1")
    assert len(providers.requests) == 2

    second = await _turn([
        _call("route", "route_request", _city_weather_route("precipitation")),
        *_city_executions("precipitation"),
        *(LLMResult(content="Paris 100 mm, Berlin 100 mm.") for _ in range(3)),
    ], message="Now compare precipitation instead.", providers=providers, evidence=evidence,
        prior=first, request_id="t2")

    # Places come from the ledger; temperature evidence is not offered for a precipitation goal.
    assert {item.kind for item in second.prior_tasks} == {"location"}
    assert not any(item.tool_name == "resolve_geospatial_location" for item in second.tool_results)
    assert len(providers.requests) == 4
    ledger = merge_ledger(
        merge_ledger([], ledger_outcomes(first, AgentLoop.completion_summary(first), now=datetime.now(UTC))),
        ledger_outcomes(second, AgentLoop.completion_summary(second), now=datetime.now(UTC)),
    )
    assert {(item.task_id, item.status) for item in ledger} == {
        ("location:paris", "completed"), ("location:berlin", "completed"),
        ("data:paris:temperature", "completed"), ("data:berlin:temperature", "completed"),
        ("data:paris:precipitation", "completed"), ("data:berlin:precipitation", "completed"),
    }


###############################################################################
LISBON_ROUTE = {"primary_domain": "place_search", "task_mode": "execute", "presentation": "map",
                "location_mode": "target", "operation": "show_location_on_map", "target_refs": ["Lisbon"]}
LISBON_PLAN = {"expected_collection_revision": 0, "actions": [
    {"action": "set_basemap", "capability_id": "osm_default"},
    {"action": "set_viewport", "strategy": "fit_location"}]}


###############################################################################
@pytest.mark.asyncio
async def test_identical_map_request_is_answered_from_the_shown_map_without_a_render() -> None:
    providers, evidence = DiscoveryProvider(), MemoryEvidence()
    first = await _turn([
        _call("route", "route_request", LISBON_ROUTE),
        _call("resolve", "resolve_geospatial_location", {"query": "Lisbon", "target_id": "Lisbon"}),
        _call("map", "apply_map_plan", LISBON_PLAN),
    ], message="Show me Lisbon on the map.", providers=providers, evidence=evidence, request_id="t1")
    assert first.prepared_map_session is not None

    second = await _turn([
        _call("route", "route_request", LISBON_ROUTE),
        _call("map", "apply_map_plan", LISBON_PLAN),
        *(LLMResult(content="The map already shows Lisbon.") for _ in range(3)),
    ], message="Show me Lisbon on the map.", providers=providers, evidence=evidence, prior=first, request_id="t2")

    shown = next(item for item in second.tool_results if item.tool_name == "apply_map_plan")
    assert isinstance(shown.data, dict) and shown.data["render_status"] == "already_shown"
    assert second.prepared_map_session is None
    assert second.termination_reason == "goal_satisfied"
    assert AgentLoop.completion_summary(second).map_state == "rendered"


###############################################################################
@pytest.mark.asyncio
async def test_map_follow_up_to_a_text_answer_is_rerouted_to_the_place_and_gets_the_map_tools() -> None:
    providers, evidence = DiscoveryProvider(), MemoryEvidence()
    first = await _turn([
        _call("route", "route_request", {**_city_weather_route("weather radar"), "target_refs": ["Paris"]}),
        _call("resolve", "resolve_geospatial_location", {"query": "Paris", "target_id": "Paris"}),
        _call("execute", "execute_geospatial_capability",
              {"capability_id": "openmeteo_weather_forecast", "location_ref": "Paris"}),
        *(LLMResult(content="Radar is not available; it is dry in Paris.") for _ in range(3)),
    ], message="Show the current weather radar over Paris.", providers=providers, evidence=evidence, request_id="t1")

    second = await _turn([
        # "Remove that layer": the router takes the earlier subject for a place.
        _call("route", "route_request", {**LISBON_ROUTE, "target_refs": ["weather radar"]}),
        _call("route-2", "route_request", {**LISBON_ROUTE, "target_refs": ["Paris"]}),
        _call("map", "apply_map_plan", LISBON_PLAN),
    ], message="Remove that layer and just show the city.", providers=providers, evidence=evidence,
        prior=first, request_id="t2")

    revision = second.route_revisions[0]
    assert revision["reason"] == "prior_subject_used_as_place" and revision["outcome"] == "revised"
    assert second.route is not None and second.route.target_refs == ["Paris"]
    assert second.prepared_map_session is not None
    assert second.prepared_map_session.resolved_location.label == "Paris"


###############################################################################
class _OffScopeProvider(DiscoveryProvider):

    # -------------------------------------------------------------------------
    async def fetch(self, provider: str, request: Any) -> ProviderResponse:
        response = await super().fetch(provider, request)
        coverage = {**(response.coverage or {}), "temporal_scope_satisfied": False}
        return replace(response, coverage=coverage)


###############################################################################
@pytest.mark.asyncio
async def test_text_answer_ends_the_run_when_no_exposed_tool_can_close_the_pending_scope() -> None:
    # S06: data was fetched but judged outside the requested window, and only
    # describe_geospatial_capability remained exposed. Corrections cannot help.
    model = _ScriptedProvider([
        _call("route", "route_request", {**_city_weather_route("wind"), "target_refs": ["Paris"], "operation": "inspect"}),
        _call("resolve", "resolve_geospatial_location", {"query": "Paris", "target_id": "Paris"}),
        _call("execute", "execute_geospatial_capability",
              {"capability_id": "openmeteo_weather_forecast", "location_ref": "Paris"}),
        *(LLMResult(content="It is breezy in Paris.") for _ in range(4)),
    ])
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="off-scope", conversation_id="off-scope",
        user_message="How windy is it in Paris right now?", context_hydrated=True,
    )
    result = await make_loop(model, _OffScopeProvider(), CityResolver()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state, budget=AgentExecutionBudget(total_seconds=10)))

    assert AgentLoop._pending_native_requirements(state) == ["temporal_scope_applied"]
    assert result.stopped_reason == "insufficient_evidence"
    assert state.no_progress_corrections == 0
    assert state.model_calls == 4


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(("complies", "answer", "calls"), [
    (True, "Paris is warmer.", 4), (True, "Both are at 100 mm.", 3), (False, "Paris is warmer.", 3),
])
async def test_stored_evidence_follow_up_gets_one_targeted_correction(complies: bool, answer: str, calls: int) -> None:
    # S12: "which of the two is warmer" over stored evidence needs one
    # transform_evidence; a model that stops without it is told exactly that
    # once, then its answer stands instead of repeating blind corrections.
    # Once the derivation closes the contract, the held-back answer is final
    # if it cites the derived figures: no second full-context synthesis.
    providers, evidence = DiscoveryProvider(), MemoryEvidence()
    first = await _turn([
        _call("route", "route_request", _city_weather_route("temperature")),
        _call("resolve-paris", "resolve_geospatial_location", {"query": "Paris", "target_id": "Paris"}),
        _call("resolve-berlin", "resolve_geospatial_location", {"query": "Berlin", "target_id": "Berlin"}),
        *_city_executions("temperature"),
        *(LLMResult(content="Paris 9 C, Berlin 9 C.") for _ in range(3)),
    ], message="What are today's temperatures in Paris and Berlin?",
        providers=providers, evidence=evidence, request_id="t1")
    fetched = len(providers.requests)
    refs = list(first.evidence_refs)

    model = _ScriptedProvider([
        _call("route", "route_request", {
            "primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "text", "location_mode": "none",
            "operation": "inspect", "analysis": {"kind": "rank", "metric": "temperature", "top_k": 2}}),
        LLMResult(content=answer),
        *([_call("transform", "transform_evidence", {"evidence_refs": refs, "operations": [
            {"op": "sort", "field": "precipitation_sum_mm", "descending": True}, {"op": "limit", "value": 2}]}),
           LLMResult(content="Paris is warmer.")] if complies else [LLMResult(content=answer)] * 3),
    ])
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="t2", conversation_id="ledger", user_message="Which is warmer?",
        context_hydrated=True, location_refs=dict(first.location_refs), evidence_refs=refs,
        prior_tasks=list(first.prior_tasks),
    )
    result = await make_loop(model, providers, CityResolver(), evidence).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state, budget=AgentExecutionBudget(total_seconds=10)))

    correction = next(item for item in state.relevant_tool_outcomes if item["observation_type"] == "pending_requirements")
    assert "transform_evidence" in correction["tools_that_close_pending"]
    assert set(correction["evidence_refs"]) <= set(refs) and correction["evidence_refs"]
    assert state.no_progress_corrections == 1
    assert len(providers.requests) == fetched
    assert [item.tool_name for item in state.tool_results].count("transform_evidence") == int(complies)
    assert result.stopped_reason == ("goal_satisfied" if complies else "insufficient_evidence")
    assert state.model_calls == calls
    phases = ["routing", "execution", "execution", "finalization"][:calls]
    assert [item["call_phase"] for item in state.context_usage_trace] == phases
    if calls == 3 and complies:
        assert result.final_text == answer


###############################################################################
@pytest.mark.asyncio
async def test_failed_derivation_after_the_targeted_correction_does_not_earn_a_second_one() -> None:
    # The failed transform widens the pending set, so the correction text
    # would differ and the identical-correction guard alone would allow another
    # one. Every pending item is still derivable from held evidence, so the one
    # correction is the cap and the next text stop finalizes.
    providers, evidence = DiscoveryProvider(), MemoryEvidence()
    first = await _turn([
        _call("route", "route_request", _city_weather_route("temperature")),
        _call("resolve-paris", "resolve_geospatial_location", {"query": "Paris", "target_id": "Paris"}),
        _call("resolve-berlin", "resolve_geospatial_location", {"query": "Berlin", "target_id": "Berlin"}),
        *_city_executions("temperature"),
        *(LLMResult(content="Paris 9 C, Berlin 9 C.") for _ in range(3)),
    ], message="What are today's temperatures in Paris and Berlin?",
        providers=providers, evidence=evidence, request_id="t1")
    refs = list(first.evidence_refs)

    model = _ScriptedProvider([
        _call("route", "route_request", {
            "primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "text", "location_mode": "none",
            "operation": "inspect", "analysis": {"kind": "rank", "metric": "temperature", "top_k": 2}}),
        LLMResult(content="Paris is warmer."),
        _call("transform", "transform_evidence", {"evidence_refs": refs, "operations": [
            {"op": "sort", "field": "no_such_field", "descending": True}, {"op": "limit", "value": 2}]}),
        *(LLMResult(content="Paris is warmer.") for _ in range(3)),
    ])
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="t2", conversation_id="ledger", user_message="Which is warmer?",
        context_hydrated=True, location_refs=dict(first.location_refs), evidence_refs=refs,
        prior_tasks=list(first.prior_tasks),
    )
    result = await make_loop(model, providers, CityResolver(), evidence).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state, budget=AgentExecutionBudget(total_seconds=10)))

    transform = next(item for item in state.tool_results if item.tool_name == "transform_evidence")
    assert transform.status == "failed"
    assert AgentLoop._pending_native_requirements(state) == [
        "result_locations_derived", "required_data_retrieved", "requested_transform_applied"]
    assert [item["observation_type"] for item in state.relevant_tool_outcomes].count("pending_requirements") == 1
    assert state.no_progress_corrections == 1
    assert state.model_calls == 4
    assert result.stopped_reason == "insufficient_evidence"


###############################################################################
@pytest.mark.asyncio
async def test_remove_layer_and_show_city_treats_the_layer_label_as_a_layer_not_a_place() -> None:
    # S16-T2: the route keeps the shown layer's label next to the city; the label
    # is a layer on the map, so it must not have to resolve as a place.
    radar = {
        "primary_domain": "data_retrieval", "secondary_domains": ["map_rendering"], "task_mode": "execute",
        "presentation": "map", "location_mode": "target", "target_refs": ["Tokyo"], "operation": "show",
        "capability_queries": ["weather radar"], "explicit_capability_ids": [],
        "temporal_scope": {"mode": "current"},
    }
    first, _ = await _raster_map_run(
        "Show the current weather radar over Tokyo.", radar, "Tokyo", "rainviewer_precipitation_radar",
        first_try="noaa_radar")
    assert first.prepared_map_session is not None
    layer = first.prepared_map_session.overlay_collection.instances[0]

    providers = _FakeProviderRegistry()
    second = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="t2", conversation_id="radar-follow-up",
        user_message="Remove that layer and just show Tokyo.", context_hydrated=True,
        location_refs=dict(first.location_refs),
        prior_tasks=merge_ledger([], ledger_outcomes(first, AgentLoop.completion_summary(first), now=datetime.now(UTC))),
        active_map_session=first.prepared_map_session,
    )
    model = _ScriptedProvider([
        _call("route", "route_request", {
            "primary_domain": "map_state", "task_mode": "execute", "presentation": "map",
            "location_mode": "target", "operation": "hide_layer", "target_refs": [layer.label, "Tokyo"],
        }),
        _call("resolve", "resolve_geospatial_location", {"query": "Tokyo", "target_id": "Tokyo"}),
        _call("map", "apply_map_plan", {"expected_collection_revision": first.prepared_map_session.overlay_collection.revision, "actions": [
            {"action": "remove_layer", "instance_id": layer.instance_id},
            {"action": "set_viewport", "strategy": "fit_location"},
        ]}),
        *(LLMResult(content="The radar layer is removed and the map shows Tokyo.") for _ in range(3)),
    ])
    await make_loop(model, providers, _PlaceResolver(), MemoryEvidence()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=second, budget=AgentExecutionBudget(total_seconds=10)))

    assert providers.requests == []
    assert second.prepared_map_session is not None
    assert second.prepared_map_session.overlay_collection.instances == []
    assert second.prepared_map_session.resolved_location.label == "Tokyo, Japan"
    assert second.termination_reason == "awaiting_render"
    # No data was requested, so the browser check must not demand a data layer per target.
    contract = presentation_contract(second, second.prepared_map_session)
    assert contract is None or contract.findings == []
    # Once the browser commits the edit, the deterministic summary names the
    # framed place and the answer check still knows a layer was removed.
    committed = second.model_copy(update={
        "active_map_session": second.prepared_map_session, "prepared_map_session": None, "render_verified": True,
    })
    summary = AgentLoop._verified_map_state_summary(committed) or ""
    assert "The map is framed on Tokyo, Japan." in summary and "Visible overlays: none." in summary
    assert layer_edit_count(committed) == 1


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "stored_coverage", "retrieved", "scoped"),
    [
        ("Tokyo", {}, True, True),
        # The map is built from Tokyo evidence but the turn asks about Portugal.
        ("Portugal", {}, False, False),
        # The stored evidence was retrieved but judged unusable when fetched.
        ("Tokyo", {"data_valid": False}, False, False),
        ("Tokyo", {"spatial_scope_satisfied": False}, True, False),
    ],
)
async def test_follow_up_map_accepts_only_covering_evidence_from_an_earlier_turn(
    target: str, stored_coverage: dict[str, Any], retrieved: bool, scoped: bool
) -> None:
    def radar_route(place: str) -> dict[str, Any]:
        return {
            "primary_domain": "data_retrieval", "secondary_domains": ["map_rendering"], "task_mode": "execute",
            "presentation": "map", "location_mode": "target", "target_refs": [place], "operation": "show",
            "capability_queries": ["weather radar"], "explicit_capability_ids": [], "temporal_scope": {"mode": "current"},
            "spatial_scope": {"kind": "administrative_geometry", "relationship": "in", "target_refs": [place]},
        }

    evidence = MemoryEvidence()
    first, _ = await _raster_map_run(
        "Show the weather radar over Tokyo.", radar_route("Tokyo"), "Tokyo", "rainviewer_precipitation_radar",
        first_try="noaa_radar", evidence=evidence,
    )
    assert first.prepared_map_session is not None
    evidence.records["evidence-1"][0].summary.setdefault("coverage", {}).update(stored_coverage)
    places = dict(first.location_refs)
    places["portugal"] = ResolvedLocation(
        label="Portugal", country="Portugal", latitude=39.5, longitude=-7.8,
        location_type="country", bbox=[-9.5, 36.9, -6.2, 42.2],
    )

    providers = _FakeProviderRegistry()
    second = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="t2", conversation_id="raster", context_hydrated=True,
        user_message="ok, render it please", location_refs=places, evidence_refs=list(first.evidence_refs),
    )
    await make_loop(_ScriptedProvider([
        _call("route", "route_request", radar_route(target)),
        _call("map", "apply_map_plan", {"expected_collection_revision": 0, "actions": [
            {"action": "set_basemap", "capability_id": "osm_default"},
            {"action": "add_evidence_layer", "capability_id": "rainviewer_precipitation_radar", "evidence_ref": "evidence-1"},
        ]}),
    ]), providers, _PlaceResolver(), evidence).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=second, budget=AgentExecutionBudget(total_seconds=10)))

    assert providers.requests == []
    assert second.prepared_map_session is not None
    checks = CompletionEvaluator.data_checks(second)
    assert checks["required_data_retrieved"] is retrieved
    assert checks["spatial_scope_applied"] is scoped


###############################################################################
_LISBON_COORDINATES_ROUTE = {"primary_domain": "place_search", "task_mode": "execute", "presentation": "text",
                             "location_mode": "target", "operation": "resolve_location", "target_refs": ["Lisbon"]}


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("synthesis", "expected"),
    [
        ("Lisbon is at 38.72 N, 9.14 W.", "38.72 N, 9.14 W"),
        ("Resolved Lisbon.", "latitude 38.72000, longitude -9.14000"),
        ("", "latitude 38.72000, longitude -9.14000"),
    ],
)
async def test_text_coordinate_lookup_delivers_the_resolved_coordinates(synthesis: str, expected: str) -> None:
    state = AgentRunState(phase=AgentPhase.RECEIVE_REQUEST, request_id="coords", conversation_id="coords",
                          user_message="What are the coordinates of Lisbon? Keep the map unchanged.", context_hydrated=True)
    model = _ScriptedProvider([
        _call("route", "route_request", _LISBON_COORDINATES_ROUTE),
        _call("resolve", "resolve_geospatial_location", {"query": "Lisbon", "target_id": "Lisbon"}),
        LLMResult(content=synthesis), LLMResult(content=synthesis),
    ])

    result = await make_loop(model, DiscoveryProvider(), CityResolver(), MemoryEvidence()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state, budget=AgentExecutionBudget(total_seconds=10)))

    assert result.stopped_reason == "goal_satisfied"
    assert expected in result.final_text
    assert state.prepared_map_session is None
    assert [item.tool_name for item in result.tool_results] == ["resolve_geospatial_location"]


###############################################################################
@pytest.mark.asyncio
async def test_text_coordinate_lookup_without_a_location_is_not_completed() -> None:
    state = AgentRunState(phase=AgentPhase.RECEIVE_REQUEST, request_id="coords-unmet", conversation_id="coords-unmet",
                          user_message="What are the coordinates of Lisbon?", context_hydrated=True)
    model = _ScriptedProvider([
        _call("route", "route_request", _LISBON_COORDINATES_ROUTE),
        *(LLMResult(content="Resolved Lisbon.") for _ in range(4)),
    ])

    result = await make_loop(model, DiscoveryProvider(), CityResolver(), MemoryEvidence()).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state, budget=AgentExecutionBudget(total_seconds=10)))

    assert result.stopped_reason != "goal_satisfied"
    assert "Not completed" in result.final_text
