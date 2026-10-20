from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from server.contracts.location import LocationSignal
from server.domain.agent.capability_route import AgentPhase, AgentRunState, AgentSpatialScope, CapabilityRoute
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.services.agent.agent_loop import AgentLoop
from server.services.agent.capability_execution import _provider_params
from server.services.agent.completion import CompletionEvaluator
from server.services.agent.location_resolver import LocationResolver, find_macro_region
from server.services.agent.native_tools import _bind_execute_request, _capability_semantic_validator
from server.services.agent.tool_definitions import ExecuteCapabilityInput, TransformEvidenceInput
from server.services.agent.tool_handlers.evidence import EvidenceToolHandler, _apply_operations, _inspect_payload
from server.services.agent.tool_registry import ToolRegistry, route_target_location_available, _data_obligation_unmet
from server.services.catalog.loader import load_macro_regions
from tests.unit.services.agent.test_native_discovery_trajectories import MemoryEvidence


def state(area: str = "Europe") -> AgentRunState:
    value = AgentRunState(request_id="test", conversation_id="test", phase=AgentPhase.BUILD_TOOL_CONTEXT,
                          user_message="Where is it hottest?")
    value.route = CapabilityRoute(primary_domain=CapabilityDomain.DATA_RETRIEVAL, task_mode="execute",
                                  presentation="map", location_mode="search_area", target_refs=[area],
                                  analysis={"kind": "rank", "metric": "temperature"})
    return value


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


def test_duplicate_macro_alias_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "reference").mkdir()
    region = {"id": "a", "name": "A", "aliases": ["shared"], "bbox": [-10, 0, 10, 10], "kind": "subregion"}
    (tmp_path / "reference/macro_regions.json").write_text(json.dumps({"macro_regions": [region, {**region, "id": "b", "name": "B"}]}))
    with pytest.raises(ValueError, match="Duplicate macro-region alias"):
        load_macro_regions(tmp_path)


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


def test_text_stop_is_no_progress_while_derived_locations_are_pending() -> None:
    value = state()
    value.context_hydrated = True
    AgentLoop._bind_search_area(value, value.route)
    AgentLoop._compile_native_goal(value, value.route)
    assert "result_locations_derived" in AgentLoop._pending_native_requirements(value)
    assert AgentLoop._evaluate_text_stop(value, value.route, "Done", available_tools=["transform_evidence"])[0] == "no_progress"


def test_analysis_requires_distinct_executes() -> None:
    value = state()
    value.route.capability_queries = ["weather", "earthquakes"]
    value.tool_results.append(ToolResult(call_id="one", tool_name="execute_geospatial_capability", status="success", summary="ok",
                                      evidence_refs=["evidence_one"], metadata=ToolExecutionMetadata(duration_ms=0, capability_id="one")))
    assert _data_obligation_unmet(value)
    # A further source stays available, but one source covering both metrics completes retrieval.
    assert CompletionEvaluator.data_checks(value)["required_data_retrieved"]
    assert _capability_semantic_validator(ExecuteCapabilityInput(capability_id="one"), value)
    assert not _capability_semantic_validator(ExecuteCapabilityInput(capability_id="two"), value)
    value.tool_results.append(value.tool_results[0].model_copy(update={"metadata": ToolExecutionMetadata(duration_ms=0, capability_id="two")}))
    assert not _data_obligation_unmet(value)


def test_raster_descriptor_does_not_close_numeric_retrieval() -> None:
    value = state()
    value.tool_results.append(ToolResult(call_id="raster", tool_name="execute_geospatial_capability", status="success", summary="descriptor",
                                      metadata=ToolExecutionMetadata(duration_ms=0, capability_id="imagery", result_type="raster")))
    assert _data_obligation_unmet(value)


def test_checkpoint_preserves_typed_intent_but_redacts_unstructured_analysis() -> None:
    from server.repositories.agent_runs import redact_trace_payload
    intent = {"kind": "rank", "metric": "rain", "order": "descending", "top_k": 5}
    payload = {"route": {"location_mode": "search_area", "analysis": intent},
               "analysis": "private reasoning", "provider": {"analysis": "private reasoning"}}
    safe = redact_trace_payload(payload)
    assert safe["route"]["analysis"] == intent
    assert "analysis" not in safe and "analysis" not in safe["provider"]
    assert "analysis" not in redact_trace_payload({"location_mode": "target", "analysis": {**intent, "thoughts": "private"}})


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


def test_discovery_prompt_requires_disclosure_and_forbids_overclaiming():
    from server.prompts.agent import build_native_agent_system_prompt
    prompt = build_native_agent_system_prompt()
    for term in ["grid_aggregate", "fit_evidence", "value_encoding", "sample count", "model estimates", "partial or excluded", "verified maximum", "evidence does not contain", "near <place_label>", "emsc_earthquakes"]:
        assert term in prompt
