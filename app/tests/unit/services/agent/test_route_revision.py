from __future__ import annotations

import json
from collections import deque
from typing import Any

import pytest

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.evidence import AgentEvidenceSummary
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.domain.geospatial.providers import ProviderResponse
from server.domain.llm.types import LLMResult, LLMToolCall
from server.contracts.geospatial import MapSession, OverlayCollectionState, ViewportPolicy
from server.services.llm.errors import LLMProviderRequestError
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.completion import describe_requirements
from server.services.agent.native_tools import register_agent_tools
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

MAP_STATE_ROUTE = {
    "primary_domain": "map_state", "task_mode": "execute", "presentation": "map",
    "operation": "restyle", "target_refs": ["earthquakes"],
}
DATA_ROUTE = {
    "primary_domain": "data_retrieval", "task_mode": "execute", "presentation": "map",
    "location_mode": "search_area", "target_refs": ["World"], "operation": "show",
    "capability_queries": ["earthquake"], "explicit_capability_ids": ["usgs_earthquakes"],
    "analysis": {"kind": "threshold", "metric": "magnitude"},
}
FILTER = {"evidence_refs": ["evidence-1"], "operations": [
    {"op": "attribute_filter", "field": "magnitude", "operator": "gte", "value": 5}]}


###############################################################################
class _Model:

    # -------------------------------------------------------------------------
    def __init__(self, results: list[LLMResult | Exception]) -> None:
        self._results = deque(results)
        self.requests: list[Any] = []

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> "_Model":
        del provider
        return self

    # -------------------------------------------------------------------------
    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        del kwargs
        self.requests.append(request)
        item = self._results.popleft()
        if isinstance(item, Exception):
            raise item
        return item


###############################################################################
def _call(call_id: str, name: str, arguments: dict[str, Any]) -> LLMResult:
    return LLMResult(content="", tool_calls=[LLMToolCall(id=call_id, name=name, arguments=arguments)])


###############################################################################
class _Evidence:

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
            byte_size=len(raw), map_eligibility="renderable",
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
class _Quakes:

    # -------------------------------------------------------------------------
    async def fetch(self, provider: str, request: Any) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id, provider_id=provider,
            payload={"features": [
                {"latitude": 10.0, "longitude": 20.0, "magnitude": 6.1},
                {"latitude": 11.0, "longitude": 21.0, "magnitude": 2.3},
            ], "value_kind": "observation"},
            result_type="features", units={"magnitude": "M"},
            coverage={"bbox": [-180, -90, 180, 90], "type": "grid_sample", "spatial_scope_satisfied": True,
                      "temporal_scope_satisfied": True},
        )


###############################################################################
def _loop(model: _Model, evidence: _Evidence) -> AgentLoop:
    capabilities = CapabilityRegistry()
    runtime = RuntimeRegistry(catalog_snapshot=capabilities.catalog_snapshot, credentials_repo=None)
    registry = ToolRegistry(runtime_registry=runtime)
    register_agent_tools(registry, capability_registry=capabilities, runtime_registry=runtime,
                         provider_registry=_Quakes(), evidence_repository=evidence,  # type: ignore[arg-type]
                         geospatial_api_service=object(), location_resolver=object())  # type: ignore[arg-type]
    return AgentLoop(provider_factory=model,  # type: ignore[arg-type]
                     capability_router=CapabilityRouter(capability_registry=capabilities, runtime_registry=runtime),
                     tool_registry=registry, tool_executor=ToolExecutor(tool_registry=registry,
                     policy_engine=PolicyEngine(capability_registry=capabilities, runtime_registry=runtime)))


###############################################################################
def _follow_up_state() -> tuple[AgentRunState, ToolResult, _Evidence]:
    """A run that follows an earthquake map: the map is active and evidence exists."""

    evidence = _Evidence()
    evidence.create(
        kind="vector", media_type="application/json", status="available",
        payload={"features": [
            {"latitude": 10.0, "longitude": 20.0, "magnitude": 6.1},
            {"latitude": 11.0, "longitude": 21.0, "magnitude": 2.3},
        ]},
        summary={}, provenance={"capability_id": "usgs_earthquakes", "units": {"magnitude": "M"}},
    )

    prior = ToolResult(
        call_id="prior-execute", tool_name="execute_geospatial_capability", status="success",
        summary="21 events", data={"kind": "features", "query": {}}, evidence_refs=["evidence-1"],
        metadata=ToolExecutionMetadata(duration_ms=0, capability_id="usgs_earthquakes", result_type="features"),
    )
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="beam", conversation_id="beam",
        user_message="Only keep those above magnitude 5", context_hydrated=True,
        evidence_refs=["evidence-1"], tool_results=[prior],
        active_map_session=MapSession(
            session_id="map-1",
            resolved_location=ResolvedLocation(label="World", latitude=0, longitude=0),
            basemap_id="osm_default", viewport=ViewportPolicy(center_latitude=0, center_longitude=0),
            basemap={"id": "osm_default", "label": "OpenStreetMap"},
            overlay_collection=OverlayCollectionState(revision=1),
        ),
    )
    return state, prior, evidence


###############################################################################
async def _run(model: _Model, state: AgentRunState, evidence: _Evidence) -> Any:
    return await _loop(model, evidence).run(AgentLoopRequest(
        provider="scripted", model="scripted", state=state,
        budget=AgentExecutionBudget(total_seconds=15, hard_max_seconds=15), max_no_progress_corrections=0))


###############################################################################
@pytest.mark.asyncio
async def test_filter_misrouted_as_restyle_is_revised_once_and_keeps_evidence() -> None:
    state, prior, evidence = _follow_up_state()
    model = _Model([
        _call("route-1", "route_request", MAP_STATE_ROUTE),
        _call("filter-1", "transform_evidence", FILTER),
        _call("route-2", "route_request", DATA_ROUTE),
        _call("filter-2", "transform_evidence", FILTER),
        LLMResult(content="Only the magnitude 6.1 event matches."),
    ])
    result = await _run(model, state, evidence)

    assert len(state.route_revisions) == 1
    revision = state.route_revisions[0]
    assert revision["outcome"] == "revised"
    assert revision["reason"] == "transform_evidence_unavailable_for_map_state_route"
    assert revision["previous_route"]["primary_domain"] == "map_state"  # type: ignore[index]
    assert state.route is not None and state.route.primary_domain is CapabilityDomain.DATA_RETRIEVAL
    assert state.goal is not None and state.goal.operation == "show"
    # Completed evidence survives the revision and feeds the corrected filter.
    assert state.tool_results[0] is prior
    assert [r.status for r in state.tool_results if r.tool_name == "transform_evidence"] == ["failed", "success"], [r.error for r in state.tool_results]
    # The data-filter route owns the request now; the map is still to be redone.
    assert result.stopped_reason != "goal_satisfied"


###############################################################################
@pytest.mark.asyncio
async def test_unfixable_filter_ends_unmet_and_revises_only_once() -> None:
    state, _, evidence = _follow_up_state()
    model = _Model([
        _call("route-1", "route_request", MAP_STATE_ROUTE),
        _call("filter-1", "transform_evidence", FILTER),
        # The revised route is still a restyle, so the filter stays inexpressible.
        _call("route-2", "route_request", MAP_STATE_ROUTE),
        _call("filter-2", "transform_evidence", FILTER),
        LLMResult(content="I applied the magnitude filter to the map."),
    ])
    result = await _run(model, state, evidence)

    assert len(state.route_revisions) == 1
    assert state.route_revisions[0]["outcome"] == "revised"
    assert result.stopped_reason != "goal_satisfied"
    assert state.prepared_map_session is None
    assert "could not be applied" in result.final_text
    assert "requested_transform_applied" in AgentLoop._pending_native_requirements(state)  # pyright: ignore[reportPrivateUsage]
    assert "filter or data operation" in describe_requirements(["requested_transform_applied"])


###############################################################################
def _revision_messages(model: _Model) -> list[dict[str, Any]]:
    request = next(
        item for item in model.requests
        if any("route_revision" in str(message.get("content")) for message in item.messages)
    )
    return [dict(message) for message in request.messages]


###############################################################################
@pytest.mark.asyncio
async def test_revision_request_is_a_well_formed_chat_completion_history() -> None:
    state, _, evidence = _follow_up_state()
    model = _Model([
        _call("route-1", "route_request", MAP_STATE_ROUTE),
        _call("filter-1", "transform_evidence", FILTER),
        _call("route-2", "route_request", DATA_ROUTE),
        LLMResult(content="done"),
    ])
    await _run(model, state, evidence)

    messages = _revision_messages(model)
    # No tool-call history: the call exposes only route_request, and the
    # failed batch has no matching tool results yet (a 400 on OpenAI-style APIs).
    assert not [m for m in messages if m.get("role") == "tool" or m.get("tool_calls")]
    assert {m["role"] for m in messages} <= {"system", "user", "assistant"}
    assert messages[-1]["role"] == "user" and "route_revision" in messages[-1]["content"]


###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("provider rejected the request"), LLMProviderRequestError(
    provider="scripted", model="scripted", stage="route_request", code="provider_bad_request", http_status=400)])
async def test_failed_revision_call_keeps_the_original_route_and_records_why(error: Exception) -> None:
    state, _, evidence = _follow_up_state()
    model = _Model([
        _call("route-1", "route_request", MAP_STATE_ROUTE),
        _call("filter-1", "transform_evidence", FILTER),
        error,
        LLMResult(content="I applied the magnitude filter to the map."),
    ])
    result = await _run(model, state, evidence)

    assert [r["outcome"] for r in state.route_revisions] == ["failed"]
    assert state.route_revisions[0]["failure_reason"]
    assert state.route is not None and state.route.primary_domain is CapabilityDomain.MAP_STATE
    assert result.stopped_reason not in {"failed", "goal_satisfied"}
    assert "could not be applied" in result.final_text
