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
from server.domain.agent.evidence import AgentEvidenceEnvelope, AgentEvidenceSummary
from server.domain.agent.map_plan import (
    AddEvidenceLayerAction,
    MapPlan,
    MarkLocationsAction,
    RemoveLayerAction,
    SetBasemapAction,
    SetLayerOpacityAction,
    SetLayerVisibilityAction,
    SetViewportAction,
)
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.services.agent.capability_execution import ToolExecutionContext
from server.services.agent.agent_loop import AgentLoop
from server.services.agent.completion import unmarked_route_targets
from server.services.agent.map_plan_service import MapPlanService, targets_outside_view
from server.services.agent.native_tools import (
    _map_plan_semantic_validator,  # pyright: ignore[reportPrivateUsage]
)
from server.services.agent.tool_definitions import ApplyMapPlanInput
from server.services.geospatial.map_session_builder import (
    viewport_covering_evidence,
    MapPlanBuildError,
    MapSessionBuilder,
)


LOCATION = ResolvedLocation(label="Zurich HB", latitude=47.378, longitude=8.540)

###############################################################################
class FakeCapabilityRegistry:

    # -------------------------------------------------------------------------
    def list_basemaps(self) -> list[dict[str, object]]:
        return [
            {"id": "basemap:osm", "metadata": {"keywords": ["street map"]}},
            {"id": "esri_world_imagery", "metadata": {"keywords": ["satellite", "satellitare"]}},
        ]

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
            "esri_world_imagery": {
                "id": "esri_world_imagery",
                "name": "Satellite Imagery",
                "provider": "arcgis",
                "type": "basemap",
                "metadata": {"tile_url": "https://tiles.example/sat/{z}/{x}/{y}"},
            },
            "places:hospitals": {
                "id": "places:hospitals",
                "name": "Hospitals",
                "provider": "overpass",
                "capabilityKind": "overlay",
                "renderingMode": "vector",
            },
            "fema_nfhl_flood_zones": {
                "id": "fema_nfhl_flood_zones",
                "name": "FEMA Flood Zones",
                "provider": "fema",
                "capabilityKind": "raster-overlay",
                "renderingMode": "raster-tile",
                "metadata": {"label": "FEMA Flood Zones"},
            },
            "SRTM_Color_Index": {
                "id": "SRTM_Color_Index",
                "name": "NASA GIBS SRTM Color Index",
                "provider": "gibs",
                "capabilityKind": "raster-overlay",
                "renderingMode": "raster-tile",
                "metadata": {"label": "NASA GIBS SRTM Color Index"},
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
        if evidence_id in {"evidence:fema", "evidence:gibs"}:
            return AgentEvidenceSummary(
                evidence_id=evidence_id,
                kind=(
                    "raster_descriptor"
                    if evidence_id == "evidence:fema"
                    else "capability_result"
                ),
                media_type="application/json",
                status="available",
                summary={"result_status": "ok", "result_type": "raster"},
                map_eligibility="renderable",
            )
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
        if evidence_id == "evidence:fema":
            summary = self.get_summary(evidence_id, conversation_id=conversation_id)
            assert summary is not None
            return summary, json.dumps(
                {
                    "renderingMode": "raster-tile",
                    "tileUrl": "https://hazards.fema.gov/export?bbox={bbox-epsg-3857}",
                }
            ).encode()
        if evidence_id == "evidence:gibs":
            summary = self.get_summary(evidence_id, conversation_id=conversation_id)
            assert summary is not None
            return summary, json.dumps(
                {
                    "layer": {"layer_id": "SRTM_Color_Index"},
                    "render": {
                        "rendering_mode": "wmts",
                        "source_protocol": "wmts",
                        "tile_url_template": (
                            "https://gibs.example/wmts/SRTM_Color_Index/"
                            "{time}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png"
                        ),
                        "layer_id": "SRTM_Color_Index",
                        "format": "image/png",
                        "tile_matrix_set": "GoogleMapsCompatible_Level9",
                        "min_zoom": 0,
                        "max_zoom": 9,
                        "default_time": "2026-06-18",
                    },
                }
            ).encode()
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

###############################################################################
class _AdmissionEvidenceRepository(FakeEvidenceRepository):

    # -------------------------------------------------------------------------
    def __init__(self, *, status: str, map_eligibility: str) -> None:
        self.status = status
        self.map_eligibility = map_eligibility

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
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
class _TwoCityEvidenceRepository(FakeEvidenceRepository):
    """One point result per compared city, as a per-target retrieval returns."""

    POINTS = {
        "evidence:zurich": (8.5410422, 47.3744489),
        "evidence:lisbon": (-9.1365919, 38.7077507),
    }

    # -------------------------------------------------------------------------
    def get_summary(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> AgentEvidenceSummary | None:
        point = self.POINTS.get(evidence_id)
        if point is None:
            return None
        return AgentEvidenceSummary(
            evidence_id=evidence_id,
            kind="vector",
            media_type="application/geo+json",
            status="available",
            summary={"feature_count": 1, "bbox": [*point, *point]},
            map_eligibility="renderable",
        )

    # -------------------------------------------------------------------------
    def get_payload(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> tuple[AgentEvidenceSummary, bytes] | None:
        summary = self.get_summary(evidence_id, conversation_id=conversation_id)
        if summary is None:
            return None
        longitude, latitude = self.POINTS[evidence_id]
        return summary, json.dumps(
            {
                "features": [
                    {
                        "id": f"{evidence_id}:point",
                        "name": "Forecast point",
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                ]
            }
        ).encode()

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
@pytest.mark.parametrize("count,extent,tight", [
    (5, [12.474, 41.896, 12.478, 41.900], True),
    (1, [12.476, 41.898, 12.476, 41.898], False),
    (5, [12.476, 41.898, 12.476, 41.898], False),
])
async def test_derived_viewport_distinguishes_nearby_results_but_keeps_single_point_guard(
    count: int, extent: list[float], tight: bool,
) -> None:
    builder = MapSessionBuilder(capability_registry=FakeCapabilityRegistry())  # type: ignore[arg-type]
    candidate = await builder.build(
        location=ResolvedLocation(label="Pantheon", latitude=41.898, longitude=12.476),
        active_session=_active_session(),
        evidence=[AgentEvidenceEnvelope(
            ok=True, status="available", evidence_ref="ranked",
            summary={"located_record_count": count, "bbox": extent},
        )],
        actions=[SetViewportAction(action="set_viewport", strategy="fit_evidence", evidence_refs=["ranked"])],
    )
    assert candidate.viewport.bbox is not None
    west, south, east, north = candidate.viewport.bbox
    if tight:
        assert east - west < 0.01 and north - south < 0.01
        assert west <= extent[0] <= extent[2] <= east
        assert south <= extent[1] <= extent[3] <= north
    else:
        assert east - west >= 0.25 and north - south >= 0.25

###############################################################################
@pytest.mark.parametrize(
    "descriptor",
    [
        {"rendering_mode": "geojson", "url": "not-a-supported-url"},
        {"rendering_mode": "geojson", "url": "http://["},
        {
            "rendering_mode": "geojson",
            "data": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {}}],
            },
        },
        {
            "rendering_mode": "geojson",
            "data": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": ["Point"],
                            "coordinates": [8.54, 47.38],
                        },
                    }
                ],
            },
        },
    ],
)
def test_render_descriptor_admission_rejects_unsafe_geojson_sources(
    descriptor: dict[str, object],
) -> None:
    with pytest.raises(MapPlanBuildError):
        MapSessionBuilder._validate_render_descriptor(descriptor)  # pyright: ignore[reportPrivateUsage]

###############################################################################
def test_render_descriptor_admission_accepts_relative_geojson_source() -> None:
    descriptor = {"rendering_mode": "geojson", "url": "/api/geospatial/layer"}

    MapSessionBuilder._validate_render_descriptor(descriptor)  # pyright: ignore[reportPrivateUsage]

###############################################################################
@pytest.mark.asyncio
async def test_raster_tile_provider_url_is_normalized_for_candidate_rendering() -> None:
    state = _state(active_map_session=_active_session())
    state.evidence_refs = ["evidence:fema"]
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                AddEvidenceLayerAction(
                    action="add_evidence_layer",
                    evidence_ref="evidence:fema",
                    capability_id="fema_nfhl_flood_zones",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    overlay = state.prepared_map_session.overlay_collection.instances[-1]
    assert overlay.capability_id == "fema_nfhl_flood_zones"
    assert (
        overlay.descriptor["tile_url_template"]
        == "/api/geospatial/tiles/fema_nfhl_flood_zones/{z}/{x}/{y}.png"
    )
    assert overlay.descriptor["url"] == overlay.descriptor["tile_url_template"]
    assert overlay.descriptor["source_url"] == (
        "https://hazards.fema.gov/export?bbox={bbox-epsg-3857}"
    )

###############################################################################
@pytest.mark.asyncio
async def test_nested_provider_raster_payload_is_admitted_for_map_plan() -> None:
    state = _state(active_map_session=_active_session())
    state.evidence_refs = ["evidence:gibs"]
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                AddEvidenceLayerAction(
                    action="add_evidence_layer",
                    evidence_ref="evidence:gibs",
                    capability_id="SRTM_Color_Index",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    overlay = state.prepared_map_session.overlay_collection.instances[-1]
    assert overlay.capability_id == "SRTM_Color_Index"
    assert overlay.descriptor["render"]["layer_id"] == "SRTM_Color_Index"
    assert overlay.descriptor["render"]["provider"] == "gibs"
    assert overlay.descriptor["tile_url_template"] == (
        "/api/geospatial/tiles/SRTM_Color_Index/{z}/{x}/{y}.png?time={time}"
    )
    assert overlay.descriptor["render"]["max_zoom"] == 9
    assert overlay.descriptor["render"]["default_time"] == "2026-06-18"
    assert overlay.descriptor["default_time"] == "2026-06-18"

###############################################################################
@pytest.mark.asyncio
async def test_apply_prepares_candidate_without_mutating_active_map() -> None:
    state = _state(active_map_session=_active_session())
    state.goal = AgentGoal(
        goal="Show recent hospitals around Zurich on the map.",
        task_mode="execute",
        presentation="both",
        operation="retrieve_recent_hospitals",
        location_mode="target",
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
        "layer_edits": 0,
        "render_status": "awaiting_render",
    }
    assert "features" not in result.model_dump(mode="json")

    # The answer names the layer with the drawn count, and flags a cut against the source count.
    state.active_map_session = state.prepared_map_session
    state.tool_results.append(ToolResult(
        call_id="execute-hospitals", tool_name="execute_geospatial_capability", status="success",
        summary="Found hospitals.", evidence_refs=["evidence:hospitals"], data={"feature_count": 1},
        metadata=ToolExecutionMetadata(capability_id="places:hospitals", duration_ms=0),
    ))
    # The later map-plan result names the same evidence but carries no count.
    state.tool_results.append(result)
    assert "(1 record)" in AgentLoop._verified_map_fallback(state)  # pyright: ignore[reportPrivateUsage]
    assert AgentLoop.completion_summary(state).truncations == []
    state.tool_results[-2].data = {"feature_count": 91}
    assert "(1 of 91 records shown)" in AgentLoop._verified_map_fallback(state)  # pyright: ignore[reportPrivateUsage]
    assert AgentLoop.completion_summary(state).truncations == [(1, 91)]

###############################################################################
@pytest.mark.asyncio
async def test_same_capability_evidence_for_two_places_keeps_both_layers_in_view() -> None:
    state = _state()
    state.evidence_refs = ["evidence:zurich", "evidence:lisbon"]
    service = MapPlanService(
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        evidence_repository=_TwoCityEvidenceRepository(),
    )

    result = await service.apply(
        MapPlan(
            expected_collection_revision=0,
            actions=[
                AddEvidenceLayerAction(
                    action="add_evidence_layer",
                    evidence_ref=ref,
                    capability_id="places:hospitals",
                )
                for ref in state.evidence_refs
            ]
            + [
                SetViewportAction(
                    action="set_viewport",
                    strategy="fit_evidence",
                    evidence_refs=list(state.evidence_refs),
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    evidence_layers = [
        instance.descriptor["evidence_ref"]
        for instance in state.prepared_map_session.overlay_collection.instances
    ]
    assert evidence_layers == ["evidence:zurich", "evidence:lisbon"]
    assert state.prepared_map_session.viewport.bbox == [
        -9.1365919,
        38.7077507,
        8.5410422,
        47.3744489,
    ]

###############################################################################
class _TimeWindowRepository(_TwoCityEvidenceRepository):
    """Two queries of one capability and place that differ only in time window."""

    POINTS = {"evidence:old": (8.54, 47.37), "evidence:new": (8.55, 47.38)}

    # -------------------------------------------------------------------------
    def get_summary(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> AgentEvidenceSummary | None:
        summary = super().get_summary(evidence_id, conversation_id=conversation_id)
        if summary is None:
            return None
        window = "2026-10-01" if evidence_id == "evidence:old" else "2026-11-05"
        query = {"operation": "list", "location_ref": "zurich", "start_time_iso": window}
        return summary.model_copy(update={"summary": {**summary.summary, "query": query}})

###############################################################################
@pytest.mark.asyncio
async def test_requery_with_a_new_time_window_replaces_the_earlier_layer() -> None:
    state = _state()
    state.evidence_refs = ["evidence:old", "evidence:new"]
    service = MapPlanService(
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        evidence_repository=_TimeWindowRepository(),
    )
    context = ToolExecutionContext(conversation_id="conversation-1")

    def plan(ref: str, revision: int) -> MapPlan:
        return MapPlan(
            expected_collection_revision=revision,
            actions=[AddEvidenceLayerAction(
                action="add_evidence_layer", evidence_ref=ref, capability_id="places:hospitals"
            )],
        )

    await service.apply(plan("evidence:old", 0), state, context)
    assert state.prepared_map_session is not None
    state.active_map_session = state.prepared_map_session
    revision = state.active_map_session.overlay_collection.revision

    result = await service.apply(plan("evidence:new", revision), state, context)

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert [
        item.descriptor["evidence_ref"]
        for item in state.prepared_map_session.overlay_collection.instances
    ] == ["evidence:new"]

###############################################################################
@pytest.mark.asyncio
async def test_an_action_on_a_superseded_layer_follows_its_replacement() -> None:
    state = _state()
    state.evidence_refs = ["evidence:old", "evidence:new"]
    service = MapPlanService(
        capability_registry=FakeCapabilityRegistry(),  # type: ignore[arg-type]
        evidence_repository=_TimeWindowRepository(),
    )
    context = ToolExecutionContext(conversation_id="conversation-1")
    first = await service.apply(MapPlan(expected_collection_revision=0, actions=[AddEvidenceLayerAction(
        action="add_evidence_layer", evidence_ref="evidence:old", capability_id="places:hospitals"
    )]), state, context)
    assert first.status == "success" and state.prepared_map_session is not None
    old_id = state.prepared_map_session.overlay_collection.instances[0].instance_id
    state.active_map_session = state.prepared_map_session

    result = await service.apply(MapPlan(
        expected_collection_revision=state.active_map_session.overlay_collection.revision,
        actions=[
            AddEvidenceLayerAction(
                action="add_evidence_layer", evidence_ref="evidence:new", capability_id="places:hospitals"
            ),
            SetLayerOpacityAction(action="set_layer_opacity", instance_id=old_id, opacity=0.5),
        ],
    ), state, context)

    assert result.status == "success"
    assert state.prepared_map_session is not None
    [layer] = state.prepared_map_session.overlay_collection.instances
    assert layer.descriptor["evidence_ref"] == "evidence:new"
    assert layer.opacity == 0.5

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
@pytest.mark.parametrize("message", ["Show me Sanremo in satellite view", "vista satellitare di Sanremo"])
async def test_location_only_plan_uses_basemap_named_by_the_user(message: str) -> None:
    state = _state()
    state.evidence_refs = []
    state.user_message = message
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
    assert state.prepared_map_session.basemap_id == "esri_world_imagery"

###############################################################################
@pytest.mark.asyncio
async def test_named_basemap_style_overrides_a_different_model_choice() -> None:
    state = _state()
    state.evidence_refs = []
    state.user_message = "Show Sanremo in satellite view"
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=0,
            actions=[
                SetBasemapAction(action="set_basemap", capability_id="basemap:osm"),
                SetViewportAction(action="set_viewport", strategy="fit_location"),
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.basemap_id == "esri_world_imagery"

###############################################################################
@pytest.mark.asyncio
async def test_named_basemap_applies_on_an_active_map_without_set_basemap() -> None:
    state = _state(
        active_map_session=_active_session().model_copy(
            update={"basemap_id": "esri_world_imagery"}
        )
    )
    state.user_message = "Go back to the street map"
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[SetViewportAction(action="set_viewport", strategy="fit_location")],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.basemap_id == "basemap:osm"

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view,action,expected",
    [
        ([8.0, 45.0, 10.0, 46.0], {"strategy": "zoom_in"}, [8.5, 45.25, 9.5, 45.75]),
        ([8.0, 45.0, 10.0, 46.0], {"strategy": "zoom_out", "steps": 2}, [5.0, 43.5, 13.0, 47.5]),
        ([8.0, 45.0, 10.0, 46.0], {"strategy": "pan", "direction": "north"}, [8.0, 45.5, 10.0, 46.5]),
        (
            [8.0, 45.0, 10.0, 46.0],
            {"strategy": "zoom_in", "anchor": "location"},
            [8.04, 47.128, 9.04, 47.628],
        ),
        # Zooming far out stops at the renderable world.
        ([-100.0, -40.0, 100.0, 40.0], {"strategy": "zoom_out", "steps": 4}, [-180.0, -85.0, 180.0, 85.0]),
    ],
)
async def test_zoom_and_pan_move_the_client_reported_view(
    view: list[float], action: dict[str, object], expected: list[float]
) -> None:
    state = _state(active_map_session=_active_session())
    state.user_message = "Zoom or pan the map"
    state.map_memory = {"current_view": {"bounds": view, "source": "client_reported"}}
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[SetViewportAction.model_validate({"action": "set_viewport", **action})],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.bounds == pytest.approx(expected)
    assert state.prepared_map_session.basemap_id == "basemap:osm"

###############################################################################
@pytest.mark.asyncio
async def test_zoom_on_the_city_centre_centres_on_the_shown_place() -> None:
    state = _state(active_map_session=_active_session())
    state.user_message = "Zoom in on the city centre"
    state.map_memory = {"current_view": {"bounds": [8.0, 45.0, 10.0, 46.0]}}
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[SetViewportAction(action="set_viewport", strategy="zoom_in")],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.center == pytest.approx(
        {"latitude": LOCATION.latitude, "longitude": LOCATION.longitude}
    )

###############################################################################
@pytest.mark.asyncio
async def test_first_map_uses_the_style_named_before_the_place_was_given() -> None:
    state = _state()
    state.evidence_refs = []
    state.user_message = "Zurich"
    state.recent_messages = [
        {"role": "user", "content": "Switch to satellite view"},
        {"role": "assistant", "content": "There is no map yet. Which place should I show?"},
    ]
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=0,
            actions=[SetViewportAction(action="set_viewport", strategy="fit_location")],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.basemap_id == "esri_world_imagery"

###############################################################################
@pytest.mark.asyncio
async def test_valid_empty_location_only_plan_carries_completion_status() -> None:
    state = _state()
    state.evidence_refs = []
    state.tool_results.append(
        ToolResult(
            call_id="execute-empty",
            tool_name="execute_geospatial_capability",
            status="valid_empty",
            summary="No alerts matched the requested extent.",
            metadata=ToolExecutionMetadata(
                capability_id="noaa_weather_alerts",
                result_status="valid_empty",
                duration_ms=0,
            ),
        )
    )

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
    assert state.prepared_map_session.payload["result_status"] == "valid_empty"

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

###############################################################################
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
        location_mode="target",
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

###############################################################################
@pytest.mark.asyncio
async def test_active_map_move_does_not_fall_back_to_prior_location() -> None:
    state = _state(active_map_session=_active_session())
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_STATE,
        task_mode="execute",
        presentation="map",
        location_mode="target",
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
    # A named but unresolved place is a tool-order correction, not a question.
    assert result.error.recovery == "choose_alternate_tool"
    assert state.prepared_map_session is None

###############################################################################
@pytest.mark.asyncio
async def test_data_layer_plan_uses_spatial_scope_location_target() -> None:
    location = ResolvedLocation(
        label="Japan",
        latitude=36.5748,
        longitude=139.2394,
    )
    state = _state(active_map_session=_active_session())
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        secondary_domains=[CapabilityDomain.DATA_RETRIEVAL],
        task_mode="execute",
        presentation="map",
        location_mode="target",
        operation="add_layer",
        target_refs=["USGS Earthquakes"],
        spatial_scope={
            "kind": "administrative_geometry",
            "relationship": "around",
            "target_refs": ["Japan"],
        },
    )
    state.location_refs = {"japan": location}

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                SetViewportAction(
                    action="set_viewport",
                    strategy="fit_location",
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.resolved_location == location

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

###############################################################################
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

###############################################################################
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

###############################################################################
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
@pytest.mark.parametrize("operation", ["set_layer_visibility", "hide"])
async def test_visibility_mutation_increments_candidate_revision(operation: str) -> None:
    state = _state(active_map_session=_active_session())
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_STATE, task_mode="execute",
        presentation="map", location_mode="none", operation=operation,
        target_refs=["Traffic"],
    )
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

###############################################################################
@pytest.mark.asyncio
async def test_unknown_layer_error_names_the_layers_on_the_map() -> None:
    state = _state(active_map_session=_active_session())
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_STATE, task_mode="execute",
        presentation="map", location_mode="none", operation="hide",
        target_refs=["Traffic"],
    )
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                SetLayerVisibilityAction(
                    action="set_layer_visibility",
                    instance_id="earthquakes_italy_30d",
                    visible=False,
                )
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.error is not None
    assert result.error.code == "unknown_layer"
    # A guessed id is answered with the real ones so the retry can differ.
    assert result.error.message.endswith("Layers on the map: traffic-1 (Traffic).")

###############################################################################
@pytest.mark.asyncio
async def test_remove_layer_mutation_removes_instance_and_increments_revision() -> None:
    state = _state(active_map_session=_active_session())
    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                RemoveLayerAction(action="remove_layer", instance_id="traffic-1")
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    assert state.prepared_map_session.overlay_collection.revision == 3
    assert state.prepared_map_session.overlay_collection.instances == []

###############################################################################
@pytest.mark.asyncio
async def test_comparison_viewport_is_widened_to_every_evidence_extent() -> None:
    builder = MapSessionBuilder(capability_registry=FakeCapabilityRegistry())  # type: ignore[arg-type]
    evidence = [
        AgentEvidenceEnvelope(ok=True, status="available", evidence_ref=ref, summary={"bbox": bbox})
        for ref, bbox in (("paris", [2.35, 48.85, 2.35, 48.85]), ("berlin", [13.4, 52.52, 13.4, 52.52]))
    ]
    candidate = await builder.build(
        location=ResolvedLocation(label="Paris", latitude=48.85, longitude=2.35),
        active_session=_active_session(),
        evidence=evidence,
        actions=[SetViewportAction(action="set_viewport", strategy="fit_location")],
    )
    west, south, east, north = viewport_covering_evidence(candidate, evidence).viewport.bbox or []

    assert west <= 2.35 and east >= 13.4 and south <= 48.85 and north >= 52.52


###############################################################################
def test_location_only_map_view_must_frame_every_requested_place() -> None:
    state = _state()
    state.location_refs = {
        "paris": ResolvedLocation(label="Paris, France", latitude=48.85, longitude=2.35),
        "berlin": ResolvedLocation(label="Berlin, Germany", latitude=52.52, longitude=13.4),
    }
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        location_mode="target",
        target_refs=["Paris", "Berlin"],
    )
    state.route = route
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]

    assert targets_outside_view(state, [2.2, 48.8, 2.5, 48.9]) == ["Berlin"]
    assert targets_outside_view(state, [2.0, 48.0, 14.0, 53.0]) == []

###############################################################################
@pytest.mark.asyncio
async def test_location_only_map_of_two_places_is_widened_to_frame_both() -> None:
    state = _state()
    state.location_refs = {
        "paris": ResolvedLocation(label="Paris, France", latitude=48.85, longitude=2.35),
        "berlin": ResolvedLocation(label="Berlin, Germany", latitude=52.52, longitude=13.4),
    }
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        location_mode="target",
        target_refs=["Paris", "Berlin"],
    )
    state.route = route
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=0,
            actions=[
                SetViewportAction(action="set_viewport", strategy="fit_location", location_ref="paris"),
                SetViewportAction(action="set_viewport", strategy="fit_location", location_ref="berlin"),
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    assert state.prepared_map_session is not None
    west, south, east, north = state.prepared_map_session.viewport.bbox or []
    assert west < 2.35 and east > 13.4 and south < 48.85 and north > 52.52

###############################################################################
@pytest.mark.asyncio
async def test_location_only_map_rejects_a_parent_standing_in_for_an_unresolved_landmark() -> None:
    state = _state()
    state.location_refs = {
        "berlin": ResolvedLocation(label="Berlin, Germany", latitude=52.52, longitude=13.4),
    }
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        location_mode="target",
        target_refs=["Brandenburg Gate"],
    )
    state.route = route
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=0,
            actions=[SetViewportAction(action="set_viewport", strategy="fit_location")],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "failed"
    assert result.error is not None and result.error.code == "target_not_resolved"
    assert state.prepared_map_session is None

###############################################################################
def _marking_state(
    places: dict[str, ResolvedLocation], targets: list[str] | None = None
) -> AgentRunState:
    state = _state(active_map_session=_active_session())
    state.user_message = "mark these places"
    state.location_refs = {"location:zurich-hb": LOCATION, **places}
    # The user zoomed in before asking: the view must survive the marking.
    state.map_memory = {"current_view": {"bounds": [8.50, 47.35, 8.58, 47.40]}}
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="map",
        location_mode="target",
        operation="mark_locations",
        target_refs=targets or list(places),
    )
    state.route = route
    AgentLoop._compile_native_goal(state, route)  # pyright: ignore[reportPrivateUsage]
    return state

###############################################################################
@pytest.mark.asyncio
async def test_marking_places_pins_them_on_the_shown_map_and_keeps_the_view() -> None:
    state = _marking_state(
        {
            "Kunsthaus": ResolvedLocation(label="Kunsthaus, Zurich", latitude=47.370, longitude=8.548),
            "Grossmunster": ResolvedLocation(label="Grossmunster, Zurich", latitude=47.370, longitude=8.544),
        },
        # A route remark in parentheses must not leave the place unresolved.
        targets=["Kunsthaus", "Grossmunster (old town)"],
    )
    assert "locations_marked" in state.completion_requirements
    assert unmarked_route_targets(state) == ["Kunsthaus", "Grossmunster (old town)"]

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[
                MarkLocationsAction(action="mark_locations", location_refs=["Kunsthaus", "Grossmunster"]),
                # A re-fit of the shown place would discard the user's zoom.
                SetViewportAction(action="set_viewport", strategy="fit_location"),
            ],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    candidate = state.prepared_map_session
    assert candidate is not None
    assert candidate.resolved_location == LOCATION
    assert candidate.viewport.bbox == pytest.approx([8.50, 47.35, 8.58, 47.40])
    markers = next(
        item for item in candidate.overlay_collection.instances
        if item.rendering_mode == "place-markers"
    )
    names = [feature["properties"]["name"] for feature in markers.descriptor["data"]["features"]]
    assert names == ["Kunsthaus", "Grossmunster"]
    assert unmarked_route_targets(state) == []
    state.active_map_session = candidate
    assert AgentLoop._verified_map_fallback(state) == (  # pyright: ignore[reportPrivateUsage]
        "Marked 2 places on the map: Kunsthaus, Grossmunster."
    )

###############################################################################
@pytest.mark.asyncio
async def test_marking_outside_the_view_frames_the_markers_under_the_requested_names() -> None:
    state = _marking_state({
        "Uetliberg": ResolvedLocation(label="Uetliberg, Zurich", latitude=47.349, longitude=8.491),
        # The geocoder answered the district with a building inside it.
        "niederdorf": ResolvedLocation(
            label="Cabaret Voltaire, Spiegelgasse, Niederdorf, Zurich",
            latitude=47.372,
            longitude=8.544,
        ),
    })

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[MarkLocationsAction(action="mark_locations", location_refs=["Uetliberg", "niederdorf"])],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )

    assert result.status == "success"
    candidate = state.prepared_map_session
    assert candidate is not None
    west, south, east, north = candidate.viewport.bbox or []
    assert west < 8.491 < 8.544 < east and south < 47.349 < 47.372 < north
    # Framed on the markers, not on the union with the old view.
    assert north < 47.40
    markers = next(
        item for item in candidate.overlay_collection.instances
        if item.rendering_mode == "place-markers"
    )
    names = [feature["properties"]["name"] for feature in markers.descriptor["data"]["features"]]
    assert names == ["Uetliberg", "Niederdorf"]

###############################################################################
@pytest.mark.asyncio
async def test_marking_route_rejects_plans_that_do_not_mark_resolved_places() -> None:
    state = _marking_state({
        "Kunsthaus": ResolvedLocation(label="Kunsthaus, Zurich", latitude=47.370, longitude=8.548),
    })
    framing_only = ApplyMapPlanInput(
        expected_collection_revision=2,
        actions=[SetViewportAction(action="set_viewport", strategy="fit_location")],
    )
    assert any(
        "mark_locations" in error
        for error in _map_plan_semantic_validator(framing_only, state)
    )

    result = await _service().apply(
        MapPlan(
            expected_collection_revision=2,
            actions=[MarkLocationsAction(action="mark_locations", location_refs=["Opera House"])],
        ),
        state,
        ToolExecutionContext(conversation_id="conversation-1"),
    )
    assert result.status == "failed"
    assert result.error is not None and result.error.code == "missing_location"

###############################################################################
def test_marking_recovery_keeps_each_place_on_its_own_lookup() -> None:
    gallery = "National Gallery of Canada, 380 Sussex Drive, Byward Market, Ottawa"
    state = _marking_state(
        {
            # The district lookup returned the gallery building inside it.
            "byward market, ottawa": ResolvedLocation(label=gallery, latitude=45.429, longitude=-75.699),
            "national gallery of canada, ottawa": ResolvedLocation(
                label=gallery, latitude=45.4295, longitude=-75.6988
            ),
        },
        targets=["ByWard Market, Ottawa", "National Gallery of Canada, Ottawa"],
    )
    assert state.route is not None

    assert AgentLoop._mark_recovery_refs(state, state.route) == [  # pyright: ignore[reportPrivateUsage]
        "byward market, ottawa",
        "national gallery of canada, ottawa",
    ]

###############################################################################
@pytest.mark.asyncio
async def test_marker_value_labels_must_come_from_the_retrieved_data() -> None:
    state = _marking_state({
        "Kunsthaus": ResolvedLocation(label="Kunsthaus, Zurich", latitude=47.370, longitude=8.548),
    })
    state.tool_results.append(ToolResult(
        call_id="weather", tool_name="execute_geospatial_capability", status="success",
        summary="ok", data={"current": {"temperature_2m": 18.3}},
        metadata=ToolExecutionMetadata(duration_ms=1),
    ))

    async def mark(label: str) -> ToolResult:
        return await _service().apply(
            MapPlan(
                expected_collection_revision=2,
                actions=[MarkLocationsAction(
                    action="mark_locations", location_refs=["Kunsthaus"], annotations={"Kunsthaus": label},
                )],
            ),
            state,
            ToolExecutionContext(conversation_id="conversation-1"),
        )

    invented = await mark("21.7 °C")
    assert invented.error is not None and invented.error.code == "annotation_not_in_evidence"

    assert (await mark("18.3 °C")).status == "success"
    markers = next(
        item for item in (state.prepared_map_session or _active_session()).overlay_collection.instances
        if item.rendering_mode == "place-markers"
    )
    properties = markers.descriptor["data"]["features"][0]["properties"]
    assert properties["name"] == "Kunsthaus: 18.3 °C" and properties["annotation"] == "18.3 °C"
