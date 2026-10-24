"""Deterministic completion checks for native data and map presentation."""

from __future__ import annotations

from typing import Any
from datetime import UTC, datetime, time, timedelta

from server.common.identifiers import location_ref_matches
from server.common.typing import json_object
from server.contracts.geospatial import MapSession
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentRunState,
    CompletionContract,
    CompletionRequirement,
)
from server.domain.agent.tool_result import EvidenceAssessment, ToolResult

###############################################################################
def _parse_scope_time(value: str, *, inclusive_end: bool = False) -> datetime:
    """Parse an ISO instant as UTC; a date-only end bound covers its whole day."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if inclusive_end and len(value.strip()) == 10:
        parsed = datetime.combine(parsed.date(), time.min, tzinfo=UTC) + timedelta(days=1)
    return parsed

###############################################################################
def _is_eligible_evidence(result: ToolResult, assessment: EvidenceAssessment, analysis: bool) -> bool:
    return bool(
        assessment.tool_execution_success and assessment.data_valid is True
        and assessment.data_relevant is True and (analysis or result.status != "partial")
    )


###############################################################################
class CompletionEvaluator:
    """Keep render obligations independent of provider or model wording."""

    # -------------------------------------------------------------------------
    @staticmethod
    def assess_evidence(state: AgentRunState, result: ToolResult) -> EvidenceAssessment:
        """Assess normalized evidence against the current server-owned goal."""
        executed = result.status != "failed" and result.error is None
        data = json_object(result.data)
        coverage = result.metadata.coverage or json_object(data.get("coverage"))
        valid = executed and bool(result.evidence_refs or (result.data and result.metadata.result_type))
        if result.status == "valid_empty":
            valid = executed and (result.semantic_outcome == "resolved" or coverage.get("query_complete") is True)
        required_ids = state.route.explicit_capability_ids if state.route else []
        relevant = bool(result.metadata.capability_id) and (
            not required_ids or result.metadata.capability_id in required_ids
        )
        if result.semantic_outcome in {"failed", "not_found", "ambiguous"}:
            valid = False
        if coverage.get("data_valid") is False:
            valid = False
        if coverage.get("data_relevant") is False:
            relevant = False
        spatial: bool | None = True
        temporal: bool | None = True
        contract = state.completion_contract
        if contract and contract.spatial_scope_required:
            spatial = coverage.get("spatial_scope_satisfied")
            if not isinstance(spatial, bool):
                spatial = None
        if contract and contract.temporal_scope_required:
            temporal = coverage.get("temporal_scope_satisfied")
            if not isinstance(temporal, bool):
                temporal = None
            scope = state.goal.temporal_scope if state.goal else {}
            expected = scope.get("reference_time_iso") or scope.get("start_time_iso")
            observed = result.metadata.observation_time
            if expected and observed:
                try:
                    start = _parse_scope_time(str(expected))
                    actual = _parse_scope_time(observed)
                    end_value = scope.get("end_time_iso")
                    end = _parse_scope_time(str(end_value), inclusive_end=True) if end_value else start
                    temporal = start <= actual <= end
                except (ValueError, TypeError):
                    temporal = None
        reasons: list[str] = []
        for name, value in (("data_valid", valid), ("data_relevant", relevant),
                            ("spatial_scope_satisfied", spatial), ("temporal_scope_satisfied", temporal)):
            if value is not True:
                reasons.append(f"{name}: {'unknown' if value is None else 'false'}; inspect evidence or discover an alternate source")
        return EvidenceAssessment(
            tool_execution_success=executed, data_valid=valid, data_relevant=relevant,
            spatial_scope_satisfied=spatial, temporal_scope_satisfied=temporal, reasons=reasons,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def data_checks(state: AgentRunState) -> dict[str, bool]:
        results = [result for result in state.tool_results if result.tool_name in {
            "execute_geospatial_capability", "inspect_evidence", "transform_evidence"
        }]
        analysis = state.route is not None and state.route.analysis is not None
        if analysis:
            results = [result for result in results if result.tool_name == "execute_geospatial_capability"
                       and result.metadata.result_type != "raster"]
        assessments = [(result, CompletionEvaluator.assess_evidence(state, result)) for result in results]
        eligible = [(result, assessment) for result, assessment in assessments
                    if _is_eligible_evidence(result, assessment, analysis)]
        required = set(state.route.explicit_capability_ids if state.route else [])
        def covered(field: str) -> bool:
            matched = {result.metadata.capability_id for result, assessment in eligible
                       if getattr(assessment, field) is True}
            # One numeric source may cover several queried metrics; the
            # registry still permits further distinct sources for analysis.
            return bool(matched) and (not required or required <= matched)
        all_targets_covered = not uncovered_route_targets(state) and not uncovered_data_obligations(state)
        return {
            "required_data_retrieved": covered("data_valid") and all_targets_covered,
            "spatial_scope_applied": covered("spatial_scope_satisfied"),
            "temporal_scope_applied": covered("temporal_scope_satisfied"),
        }

    _RENDER_REQUIREMENTS = (
        "map_state_committed",
        "viewport_contains_results",
        "final_response_ready",
        "render_verified",
    )

    # -------------------------------------------------------------------------
    @staticmethod
    def native_candidate_requirements(
        *,
        completion_contract: CompletionContract | None,
        goal: AgentGoal | None,
        map_session: MapSession,
    ) -> list[CompletionRequirement]:
        """Build render obligations from the native goal contract.

        Render acknowledgment is a continuation of the native run. It must
        not rehydrate a removed interpretation pipeline merely to decide
        whether a map candidate is renderable.
        """

        required_names = list(
            completion_contract.requirements if completion_contract is not None else []
        )
        for name in (
            "location_resolved",
            "required_data_retrieved",
            "temporal_scope_applied",
            "spatial_scope_applied",
            "map_candidate_prepared",
        ):
            if (
                completion_contract is not None
                and getattr(completion_contract, f"{_native_flag(name)}_required", False)
                and name not in required_names
            ):
                required_names.append(name)
        for name in CompletionEvaluator._RENDER_REQUIREMENTS:
            if name not in required_names:
                required_names.append(name)

        data_failure = any(
            str(
                instance.descriptor.get("result_status")
                or instance.descriptor.get("resultStatus")
                or instance.descriptor.get("render_status")
                or instance.descriptor.get("renderStatus")
                or ""
            ).casefold()
            in {"unavailable", "error", "failed", "invalid"}
            for instance in map_session.overlay_collection.instances
        )
        valid_empty = (
            str(
                map_session.payload.get("result_status")
                or map_session.payload.get("resultStatus")
                or ""
            ).casefold()
            == "valid_empty"
        )
        values = {
            "location_resolved": True,
            "search_area_bound": True,
            "result_locations_derived": True,
            # A map is prepared only after the loop's own checks; measurement
            # is not re-evaluated by the browser.
            "measurement_computed": True,
            "required_data_retrieved": not data_failure
            and bool(
                map_session.overlay_collection.instances
                or valid_empty
            ),
            "temporal_scope_applied": _native_temporal_scope_applied(
                goal,
                map_session,
                evidence_required=(
                    completion_contract is None or completion_contract.evidence_required
                ),
            ),
            "spatial_scope_applied": _native_spatial_scope_applied(goal, map_session),
            "map_candidate_prepared": True,
            "map_state_committed": False,
            "viewport_contains_results": False,
            "final_response_ready": False,
            "render_verified": False,
        }
        return [
            CompletionRequirement(
                name=name,
                required=True,
                status=(
                    "satisfied"
                    if values.get(name, False)
                    else "failed"
                    if name == "required_data_retrieved" and data_failure
                    else "pending"
                ),
                evidence_ref=f"map_session:{map_session.session_id}",
            )
            for name in required_names
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def acknowledge_requirements(
        requirements: list[dict[str, Any]],
        acknowledgment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply a browser render acknowledgment to native obligations."""

        checks = json_object(acknowledgment.get("checks"))
        ready = acknowledgment.get("status") == "ready"
        updated: list[dict[str, Any]] = []
        for raw in requirements:
            item = dict(raw)
            name = str(item.get("name") or "")
            if name == "map_state_committed":
                item["status"] = "satisfied" if ready else "failed"
            elif name == "viewport_contains_results":
                item["status"] = (
                    "satisfied"
                    if ready and checks.get("viewport_valid") is True
                    else "failed" if not ready else "pending"
                )
            elif name == "final_response_ready":
                item["status"] = "satisfied" if ready else "failed"
            elif name == "render_verified":
                item["status"] = "satisfied" if ready else "failed"
            updated.append(item)
        return updated

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_renderable_output(map_session: MapSession) -> bool:
        instances = map_session.overlay_collection.instances
        if not instances:
            # Empty provider results can still render a valid analysis area.
            return bool(map_session.bounds or map_session.viewport)
        for instance in instances:
            mode = str(instance.rendering_mode).casefold()
            descriptor = instance.descriptor
            render_status = str(
                descriptor.get("render_status")
                or descriptor.get("renderStatus")
                or ""
            ).casefold()
            result_type = str(
                descriptor.get("result_type") or descriptor.get("resultType") or ""
            ).casefold()
            if (
                mode not in {"metadata-only", "metadata_only"}
                and result_type != "metadata"
                and render_status not in {"unavailable", "invalid", "error", "failed"}
            ):
                return True
        return False

###############################################################################
def _native_flag(name: str) -> str:
    return {
        "location_resolved": "location",
        "search_area_bound": "location",
        "result_locations_derived": "evidence",
        "required_data_retrieved": "evidence",
        "temporal_scope_applied": "temporal_scope",
        "spatial_scope_applied": "spatial_scope",
        "map_candidate_prepared": "map_preparation",
    }.get(name, name)

###############################################################################
def _native_temporal_scope_applied(
    goal: AgentGoal | None,
    map_session: MapSession,
    *,
    evidence_required: bool = True,
) -> bool:
    if goal is None or not goal.temporal_scope:
        return True
    expected_mode = str(goal.temporal_scope.get("mode") or "none")
    if expected_mode == "none":
        return True
    instances = map_session.overlay_collection.instances
    if not instances:
        # Without required evidence (for example a basemap-only imagery view)
        # there is no data layer a temporal scope could be applied to.
        return not evidence_required or (
            str(
                map_session.payload.get("result_status")
                or map_session.payload.get("resultStatus")
                or ""
            ).casefold()
            == "valid_empty"
        )
    temporal_instances = [
        instance
        for instance in instances
        if str(
            instance.descriptor.get("temporal_mode")
            or instance.descriptor.get("time_mode")
            or ""
        ).strip()
    ]
    return bool(temporal_instances) and all(
        str(
            instance.descriptor.get("temporal_mode")
            or instance.descriptor.get("time_mode")
            or ""
        ).strip()
        == expected_mode
        for instance in temporal_instances
    )

###############################################################################
def _native_spatial_scope_applied(
    goal: AgentGoal | None, map_session: MapSession
) -> bool:
    if goal is None or not goal.spatial_scope:
        return True
    instances = map_session.overlay_collection.instances
    if not instances:
        return bool(map_session.bounds or map_session.viewport)
    expected_kinds = {
        str(item.get("kind") or item.get("analysis_scope") or "")
        for item in goal.spatial_scope
    }
    declared = {
        str(
            instance.descriptor.get("analysis_scope")
            or instance.descriptor.get("scope_kind")
            or ""
        )
        for instance in instances
    }
    return not expected_kinds or bool(expected_kinds.intersection(declared))


###############################################################################
def uncovered_data_obligations(state: AgentRunState) -> list[str]:
    """Return requested analytical components without validated evidence yet.

    One source may satisfy several obligations when its manifest covers them;
    the model still chooses the sources and their order.
    """

    contract = state.completion_contract
    if contract is None or not contract.data_obligations:
        return []
    analysis = state.route is not None and state.route.analysis is not None
    covered: set[str] = set()
    for result in state.tool_results:
        if result.tool_name != "execute_geospatial_capability" or not result.metadata.covered_queries:
            continue
        if analysis and result.metadata.result_type == "raster":
            continue
        if _is_eligible_evidence(result, CompletionEvaluator.assess_evidence(state, result), analysis):
            covered.update(result.metadata.covered_queries)
    return [query for query in contract.data_obligations if query not in covered]


###############################################################################
def uncovered_route_targets(state: AgentRunState) -> list[str]:
    """Return resolved route targets that no data execution has covered yet.

    A comparison such as "Paris and Berlin" needs data for each place; one
    successful execution must not satisfy the whole route. Single-target and
    analysis routes keep their own coverage rules.
    """

    route = state.route
    if (
        route is None
        or route.analysis is not None
        or route.location_mode != "target"
        or len(route.target_refs) < 2
    ):
        return []
    covered_keys = {
        str(json_object(json_object(result.data).get("query")).get("location_ref") or "").strip()
        for result in state.tool_results
        if result.tool_name == "execute_geospatial_capability"
        and _is_eligible_evidence(result, CompletionEvaluator.assess_evidence(state, result), False)
    }
    uncovered: list[str] = []
    for target in route.target_refs:
        matches = [
            key
            for key, location in state.location_refs.items()
            if location_ref_matches(str(target), str(key), location.label)
        ]
        if matches and not covered_keys.intersection(matches):
            uncovered.append(str(target))
    return uncovered


###############################################################################
def follow_up_location_keys(state: AgentRunState) -> set[str]:
    """Return points this run resolved inside a goal target's area.

    An investigation may find a place first (the strongest earthquake in
    Europe) and then query another source there.  Such a point is not a goal
    target, but it stays within the requested geography, so later steps may
    use it; any other location is still never substituted for the target.
    """

    goal = state.goal
    if goal is None or not goal.target_ids:
        return set()

    def is_goal_target(key: str, label: str) -> bool:
        return any(location_ref_matches(str(target), key, label) for target in goal.target_ids)

    areas = [
        location.bbox
        for key, location in state.location_refs.items()
        if location.bbox and len(location.bbox) == 4 and is_goal_target(str(key), location.label)
    ]
    keys: set[str] = set()
    for result in state.tool_results:
        if result.tool_name != "resolve_geospatial_location" or result.status != "success":
            continue
        key = str(json_object(result.data).get("target_id") or "")
        location = state.location_refs.get(key)
        if location is None or is_goal_target(key, location.label):
            continue
        if any(
            area[0] <= location.longitude <= area[2] and area[1] <= location.latitude <= area[3]
            for area in areas
        ):
            keys.add(key)
    return keys


__all__ = [
    "CompletionEvaluator",
    "follow_up_location_keys",
    "uncovered_data_obligations",
    "uncovered_route_targets",
]
