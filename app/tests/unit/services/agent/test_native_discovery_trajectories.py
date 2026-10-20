"""Intent discovery using the real route, registry, execution and map boundaries."""
from __future__ import annotations

import json
from typing import Any

import pytest

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.evidence import AgentEvidenceSummary
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.geospatial.providers import ProviderResponse
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.native_tools import register_agent_tools
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.domain.agent.decision import ClarificationRequest, ResolvedLocation
from server.domain.llm.types import LLMResult
from server.services.geospatial.providers.base import ProviderUnavailableError
from tests.unit.services.agent.test_native_gibs_trajectory import _call, _ProviderFactory, _ScriptedProvider


class MemoryEvidence:
    def __init__(self) -> None:
        self.records: dict[str, tuple[AgentEvidenceSummary, bytes]] = {}

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

    def get_payload(self, ref: str, **kwargs: Any) -> tuple[AgentEvidenceSummary, bytes] | None:
        return self.records.get(ref)

    def get_summary(self, ref: str, **kwargs: Any) -> AgentEvidenceSummary | None:
        record = self.records.get(ref)
        return record[0] if record else None


class DiscoveryProvider:
    def __init__(self, *, partial: bool = False) -> None:
        self.requests: list[Any] = []
        self.partial = partial

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


def make_loop(model: _ScriptedProvider, providers: Any, resolver: Any = None) -> AgentLoop:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(catalog_snapshot=capabilities.catalog_snapshot, credentials_repo=None)
    registry = ToolRegistry(runtime_registry=runtime)
    register_agent_tools(registry, capability_registry=capabilities, runtime_registry=runtime,
                         provider_registry=providers, evidence_repository=MemoryEvidence(),
                         geospatial_api_service=object(), location_resolver=resolver or LocationResolver())
    return AgentLoop(provider_factory=_ProviderFactory(model),
                     capability_router=CapabilityRouter(capability_registry=capabilities, runtime_registry=runtime),
                     tool_registry=registry, tool_executor=ToolExecutor(tool_registry=registry,
                     policy_engine=PolicyEngine(capability_registry=capabilities, runtime_registry=runtime)))


@pytest.mark.asyncio
@pytest.mark.parametrize("place", ["Springfield", "Florence"])
async def test_ambiguous_place_still_clarifies(place: str) -> None:
    class Resolver:
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


@pytest.mark.asyncio
async def test_direct_paris_weather_map_is_unchanged() -> None:
    class Resolver:
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


@pytest.mark.asyncio
async def test_failed_discovery_provider_has_no_map() -> None:
    class FailingProvider:
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


@pytest.mark.asyncio
async def test_stale_lyon_does_not_bind_italy_search_area() -> None:
    class Resolver:
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
    assert providers.requests[0].time is not None
    assert state.prepared_map_session is not None
    descriptor = state.prepared_map_session.overlay_collection.instances[-1].descriptor
    assert descriptor["value_encoding"]["max"] == (1 if seismic else 100)
    # One derived point fits at city scale rather than maximum zoom.
    viewport_bbox = state.prepared_map_session.viewport.bbox
    assert viewport_bbox is not None and min(viewport_bbox[2] - viewport_bbox[0], viewport_bbox[3] - viewport_bbox[1]) >= 0.25
    assert evidence.records["evidence-2"][0].provenance["units"][field]
