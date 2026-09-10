from __future__ import annotations

import pytest

from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    OverlayInstance,
    ViewportPolicy,
)
from server.domain.agent.capability_route import AgentPhase, AgentState
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.evidence import AgentEvidenceSummary
from server.domain.agent.map_plan import (
    AddEvidenceLayerAction,
    MapPlan,
    SetLayerVisibilityAction,
    SetViewportAction,
)
from server.services.agent.capability_execution import ToolExecutionContext
from server.services.agent.map_plan_service import MapPlanService


LOCATION = ResolvedLocation(label="Zurich HB", latitude=47.378, longitude=8.540)


class FakeCapabilityRegistry:
    def list_basemaps(self) -> list[dict[str, object]]:
        return [{"id": "basemap:osm"}]

    def get_capability(self, capability_id: str) -> dict[str, object] | None:
        values = {
            "basemap:osm": {
                "id": "basemap:osm",
                "name": "OpenStreetMap",
                "provider": "osm",
                "type": "basemap",
                "metadata": {"tile_url": "https://tiles.example/{z}/{x}/{y}"},
            },
            "places:hospitals": {
                "id": "places:hospitals",
                "name": "Hospitals",
                "provider": "overpass",
                "capabilityKind": "overlay",
                "renderingMode": "vector",
            },
        }
        return values.get(capability_id)


class FakeEvidenceRepository:
    def get_summary(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> AgentEvidenceSummary | None:
        if evidence_id != "evidence:hospitals":
            return None
        return AgentEvidenceSummary(
            evidence_id=evidence_id,
            kind="vector",
            media_type="application/geo+json",
            status="available",
            summary={"feature_count": 2, "bbox": [8.50, 47.35, 8.60, 47.41]},
            map_eligibility="renderable",
        )


def _state(
    *,
    active_map_session: MapSession | None = None,
    phase: AgentPhase = AgentPhase.BUILD_TOOL_CONTEXT,
) -> AgentState:
    return AgentState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=phase,
        user_message="show hospitals",
        location_refs={"location:zurich-hb": LOCATION},
        evidence_refs=["evidence:hospitals"],
        active_map_session=active_map_session,
    )


def _active_session() -> MapSession:
    return MapSession(
        session_id="active-map",
        resolved_location=LOCATION,
        basemap_id="basemap:osm",
        viewport=ViewportPolicy(
            center_latitude=LOCATION.latitude,
            center_longitude=LOCATION.longitude,
        ),
        basemap={"id": "basemap:osm"},
        overlay_collection=OverlayCollectionState(
            revision=2,
            instances=[
                OverlayInstance(
                    instance_id="traffic-1",
                    capability_id="traffic",
                    label="Traffic",
                    provider="traffic",
                    overlay_type="vector",
                    rendering_mode="vector",
                )
            ],
        ),
    )


def _service() -> MapPlanService:
    return MapPlanService(
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        evidence_repository=FakeEvidenceRepository(),
    )


@pytest.mark.asyncio
async def test_apply_prepares_candidate_without_mutating_active_map() -> None:
    state = _state(active_map_session=_active_session())
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
                actions=[
                AddEvidenceLayerAction(
                    action="add_evidence_layer",
                    evidence_ref="evidence:hospitals",
                    capability_id="places:hospitals",
                ),
                SetViewportAction(
                    action="set_viewport",
                    strategy="fit_evidence",
                    evidence_refs=["evidence:hospitals"],
                ),
            ],
        ),
        state,
        ToolExecutionContext(
            conversation_id="conversation-1",
            call_id="call-map-1",
        ),
    )

    assert result.status == "success"
    assert result.map_candidate_id is not None
    assert state.active_map_session is not None
    assert state.active_map_session.overlay_collection.revision == 2
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.overlay_collection.revision == 3
    assert result.data == {
        "map_candidate_id": result.map_candidate_id,
        "collection_revision": 3,
        "basemap_id": "basemap:osm",
        "overlay_count": 2,
        "render_status": "awaiting_render",
    }
    assert "features" not in result.model_dump(mode="json")


@pytest.mark.asyncio
async def test_location_only_plan_gets_catalog_default_basemap() -> None:
    state = _state()
    state.evidence_refs = []
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=0,
            actions=[
                SetViewportAction(action="set_viewport", strategy="fit_location"),
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.basemap_id == "basemap:osm"
    assert state.prepared_map_session.overlay_collection.instances == []


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_without_candidate() -> None:
    state = _state(active_map_session=_active_session())
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=1,
                actions=[
                SetLayerVisibilityAction(
                    action="set_layer_visibility",
                    instance_id="traffic-1",
                    visible=False,
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "stale_map_revision"
    assert state.prepared_map_session is None


@pytest.mark.asyncio
async def test_missing_evidence_is_rejected() -> None:
    state = _state(active_map_session=_active_session())
    state.evidence_refs = []
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
                actions=[
                AddEvidenceLayerAction(
                    action="add_evidence_layer",
                    evidence_ref="evidence:hospitals",
                    capability_id="places:hospitals",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "unknown_evidence"


@pytest.mark.asyncio
async def test_visibility_mutation_increments_candidate_revision() -> None:
    state = _state(active_map_session=_active_session())
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
                actions=[
                SetLayerVisibilityAction(
                    action="set_layer_visibility",
                    instance_id="traffic-1",
                    visible=False,
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.overlay_collection.revision == 3
    assert state.prepared_map_session.overlay_collection.instances[0].visible is False
