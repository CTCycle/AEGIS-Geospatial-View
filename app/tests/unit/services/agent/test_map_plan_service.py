from __future__ import annotations

import json

import pytest

from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    OverlayInstance,
    ViewportPolicy,
)
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentPhase,
    AgentRunState,
    CapabilityRoute,
)
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


###############################################################################
class FakeCapabilityRegistry:

    # -------------------------------------------------------------------------
    def list_basemaps(self) -> list[dict[str, object]]:
        return [{"id": "basemap:osm"}]

    # -------------------------------------------------------------------------
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
            "broken:vector-tile": {
                "id": "broken:vector-tile",
                "name": "Broken vector tile",
                "provider": "natural-earth",
                "capabilityKind": "overlay",
                "renderingMode": "vector-tile",
            },
        }
        return values.get(capability_id)


###############################################################################
class FakeEvidenceRepository:

    # -------------------------------------------------------------------------
    def get_summary(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> AgentEvidenceSummary | None:
        if evidence_id != "evidence:hospitals":
            if evidence_id == "evidence:metadata":
                return AgentEvidenceSummary(
                    evidence_id=evidence_id,
                    kind="diagnostic",
                    media_type="application/json",
                    status="available",
                    map_eligibility="not_renderable",
                )
            return None
        return AgentEvidenceSummary(
            evidence_id=evidence_id,
            kind="vector",
            media_type="application/geo+json",
            status="available",
            summary={"feature_count": 2, "bbox": [8.50, 47.35, 8.60, 47.41]},
            map_eligibility="renderable",
        )

    # -------------------------------------------------------------------------
    def get_payload(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> tuple[AgentEvidenceSummary, bytes] | None:
        if evidence_id != "evidence:hospitals":
            return None
        summary = self.get_summary(evidence_id, conversation_id=conversation_id)
        if summary is None:
            return None
        return summary, json.dumps(
            {
                "features": [
                    {
                        "id": "hospital-1",
                        "name": "Test Hospital",
                        "latitude": 47.38,
                        "longitude": 8.54,
                    }
                ]
            }
        ).encode()


class _AdmissionEvidenceRepository(FakeEvidenceRepository):

    def __init__(self, *, status: str, map_eligibility: str) -> None:
        self.status = status
        self.map_eligibility = map_eligibility

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
            status=self.status,  # type: ignore[arg-type]
            summary={"feature_count": 1},
            map_eligibility=self.map_eligibility,  # type: ignore[arg-type]
        )

    def get_payload(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> tuple[AgentEvidenceSummary, bytes] | None:
        summary = self.get_summary(evidence_id, conversation_id=conversation_id)
        if summary is None:
            return None
        return summary, json.dumps({"features": [{"id": "hospital-1"}]}).encode()


###############################################################################
def _state(
    *,
    active_map_session: MapSession | None = None,
    phase: AgentPhase = AgentPhase.BUILD_TOOL_CONTEXT,
) -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=phase,
        user_message="show hospitals",
        location_refs={"location:zurich-hb": LOCATION},
        evidence_refs=["evidence:hospitals"],
        active_map_session=active_map_session,
    )


###############################################################################
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


###############################################################################
def _service() -> MapPlanService:
    return MapPlanService(
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        evidence_repository=FakeEvidenceRepository(),
    )


###############################################################################
@pytest.mark.asyncio
async def test_apply_prepares_candidate_without_mutating_active_map() -> None:
    state = _state(active_map_session=_active_session())
    state.goal = AgentGoal(
        goal="Show recent hospitals around Zurich on the map.",
        task_mode="execute",
        presentation="both",
        operation="retrieve_recent_hospitals",
        requires_location=True,
        target_ids=["Zurich"],
        temporal_scope={"mode": "historical", "granularity": "recent"},
        spatial_scope=[
            {
                "kind": "radius",
                "relationship": "around",
                "target_refs": ["Zurich"],
            }
        ],
    )
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
    overlay = state.prepared_map_session.overlay_collection.instances[-1]
    assert overlay.descriptor["data"]["type"] == "FeatureCollection"
    assert overlay.descriptor["data"]["features"][0]["id"] == "hospital-1"
    assert overlay.descriptor["temporal_mode"] == "historical"
    assert overlay.descriptor["temporal_granularity"] == "recent"
    assert overlay.descriptor["analysis_scope"] == "radius"
    assert result.data == {
        "map_candidate_id": result.map_candidate_id,
        "collection_revision": 3,
        "basemap_id": "basemap:osm",
        "overlay_count": 2,
        "render_status": "awaiting_render",
    }
    assert "features" not in result.model_dump(mode="json")


###############################################################################
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


###############################################################################
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
async def test_active_map_move_uses_the_validated_new_route_target() -> None:
    salta = ResolvedLocation(
        label="Salta, Argentina", latitude=-24.7821, longitude=-65.4232
    )
    state = _state(active_map_session=_active_session())
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_STATE,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        target_refs=["Salta, Argentina"],
    )
    state.location_refs = {"salta, argentina": salta}

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                SetViewportAction(
                    action="set_viewport",
                    strategy="fit_location",
                    location_ref="Salta, Argentina",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.resolved_location == salta
    assert state.prepared_map_session.center == {
        "latitude": salta.latitude,
        "longitude": salta.longitude,
    }


@pytest.mark.asyncio
async def test_active_map_move_does_not_fall_back_to_prior_location() -> None:
    state = _state(active_map_session=_active_session())
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_STATE,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        target_refs=["Salta, Argentina"],
    )

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                SetViewportAction(
                    action="set_viewport",
                    strategy="fit_location",
                    location_ref="Salta, Argentina",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "missing_location"
    assert state.prepared_map_session is None


###############################################################################
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
async def test_not_renderable_evidence_is_rejected_before_candidate_build() -> None:
    state = _state(active_map_session=_active_session())
    state.evidence_refs = ["evidence:metadata"]
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                AddEvidenceLayerAction(
                    action="add_evidence_layer",
                    evidence_ref="evidence:metadata",
                    capability_id="places:hospitals",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "evidence_not_renderable"
    assert state.prepared_map_session is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "map_eligibility"),
    [("valid_empty", "renderable"), ("available", "unknown")],
)
async def test_non_usable_evidence_cannot_satisfy_a_requested_layer(
    status: str,
    map_eligibility: str,
) -> None:
    state = _state(active_map_session=_active_session())
    repository = _AdmissionEvidenceRepository(
        status=status,
        map_eligibility=map_eligibility,
    )
    service = MapPlanService(
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        evidence_repository=repository,
    )

    result = await service.apply(
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
    assert result.error.code == "evidence_not_renderable"
    assert state.prepared_map_session is None


@pytest.mark.asyncio
async def test_vector_tile_descriptor_without_source_metadata_is_rejected() -> None:
    state = _state(active_map_session=_active_session())
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                AddEvidenceLayerAction(
                    action="add_evidence_layer",
                    evidence_ref="evidence:hospitals",
                    capability_id="broken:vector-tile",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "render_descriptor_unavailable"
    assert state.prepared_map_session is None


###############################################################################
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
