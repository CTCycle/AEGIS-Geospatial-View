from __future__ import annotations

from collections import deque
import json
from typing import Any

import pytest

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.evidence import AgentEvidenceSummary
from server.domain.agent.reliability import AgentExecutionBudget
from server.domain.geospatial.providers import ProviderResponse
from server.domain.llm.types import LLMResult, LLMToolCall
from server.services.agent.agent_loop import AgentLoop, AgentLoopRequest
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.native_tools import register_agent_tools
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_executor import ToolExecutor
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry


class _ScriptedProvider:
    def __init__(self, results: list[LLMResult]) -> None:
        self._results = deque(results)

    async def achat(self, request: Any, **kwargs: Any) -> LLMResult:
        del request, kwargs
        return self._results.popleft()


class _ProviderFactory:
    def __init__(self, provider: _ScriptedProvider) -> None:
        self.provider = provider

    def get_provider(self, provider: str) -> _ScriptedProvider:
        del provider
        return self.provider


class _FakeLocationResolver:
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


class _FakeProviderRegistry:
    def __init__(self) -> None:
        self.requests: list[Any] = []

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


class _FakeEvidenceRepository:
    def __init__(self) -> None:
        self._records: dict[str, tuple[AgentEvidenceSummary, bytes]] = {}

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

    def get_summary(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> AgentEvidenceSummary | None:
        del conversation_id
        record = self._records.get(evidence_id)
        return record[0] if record else None

    def get_payload(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> tuple[AgentEvidenceSummary, bytes] | None:
        del conversation_id
        return self._records.get(evidence_id)


def _call(call_id: str, name: str, arguments: dict[str, Any]) -> LLMResult:
    return LLMResult(
        content="",
        tool_calls=[LLMToolCall(id=call_id, name=name, arguments=arguments)],
    )


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
                    "requires_location": True,
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
