"""Deterministic completion checks for native data and map presentation."""

from __future__ import annotations

import re
from typing import Any
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from server.common.identifiers import location_ref_matches, normalize_target_key
from server.common.typing import json_array, json_object
from server.contracts.geospatial import MapSession
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentRunState,
    CompletionContract,
    CompletionRequirement,
    ConversationTask,
    ConversationTaskStatus,
    ObligationKind,
    RequestObligation,
    TargetRequirement,
    obligation_requirement,
)
from server.domain.agent.map_plan import (
    PLACE_MARKERS_INSTANCE_ID,
    is_mark_locations_operation,
)
from server.domain.agent.presentation_contract import (
    CompletionSummary,
    ContractTarget,
    MapState,
    ObligationOutcome,
    ObligationStatus,
    PresentationContract,
)
from server.domain.agent.task_ledger import map_fingerprint
from server.domain.agent.tool_result import EvidenceAssessment, ToolResult
from server.services.agent.policy_engine import is_text_location_lookup
from server.services.agent.route_references import place_targets

###############################################################################
def _parse_scope_time(value: str, *, inclusive_end: bool = False) -> datetime:
    """Parse an ISO instant as UTC; a date-only end bound covers its whole day."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if inclusive_end and len(value.strip()) == 10:
        parsed = datetime.combine(parsed.date(), time.min, tzinfo=UTC) + timedelta(days=1)
    return parsed

CURRENT_TOLERANCE = timedelta(hours=2)
_NUMERIC_AGGREGATIONS = frozenset({
    "maximum", "max", "minimum", "min", "mean", "average", "avg", "sum", "total", "median", "count",
})

# Error code of a transform on evidence that is raster imagery without records.
RASTER_ONLY_CODE = "unsupported_evidence_records"

###############################################################################
def needs_numeric_values(state: AgentRunState) -> bool:
    """Whether the request asks for computed values, not for imagery.

    An analysis route or a maximum/minimum/average over a period is answered
    by numeric records. A raster layer only paints a field: it carries no
    values to rank, compare or aggregate, so it never satisfies such a request.
    """

    route = state.route
    if route is None:
        return False
    return route.analysis is not None or (
        route.temporal_scope.aggregation.strip().casefold() in _NUMERIC_AGGREGATIONS
    )

###############################################################################
def analysis_unsupported(state: AgentRunState) -> bool:
    """Whether the route's analysis needs records that no available source returned.

    The route asks for values (a ranking, count or aggregate) and shows a map,
    every shortlisted source has run, and each answered with raster imagery:
    imagery carries no records to analyse, so the analysis is settled as
    unsupported (disclosed, never silently dropped) and the imagery can be
    shown. Sources that have not run yet may still return records, so the
    analysis stays open until the shortlist is exhausted.
    """

    route = state.route
    if route is None or route.presentation not in {"map", "both"} or not needs_numeric_values(state):
        return False
    executed = _imagery_only_executions(state)
    settled = {result.metadata.capability_id for result in executed} | set(state.excluded_capability_ids)
    return bool(executed and state.capability_ids) and set(state.capability_ids) <= settled

###############################################################################
def _imagery_only_executions(state: AgentRunState) -> list[ToolResult]:
    """The run's capability executions when every one returned raster imagery, else none."""

    executed = [
        result for result in state.tool_results
        if result.tool_name == "execute_geospatial_capability" and result.status != "failed"
    ]
    return [] if any(result.metadata.result_type != "raster" for result in executed) else executed

###############################################################################
def imagery_only_note(state: AgentRunState) -> str:
    """Name the gap when only raster imagery answered a request for values."""

    if not needs_numeric_values(state) or state.route is None or not _imagery_only_executions(state):
        return ""
    query = state.route.capability_queries[0] if state.route.capability_queries else ""
    aggregation = state.route.temporal_scope.aggregation
    subject = query if aggregation == "none" or aggregation in query else f"{aggregation} {query}".strip()
    return (
        "Only map imagery layers were available for this request. They carry no numeric values, "
        f"so the requested {subject or 'values'} could not be computed or compared."
    )

###############################################################################
def _result_location_ref(result: ToolResult) -> str:
    """Name the target a result belongs to: its query, else its first source."""

    query_ref = json_object(json_object(result.data).get("query")).get("location_ref")
    if query_ref:
        return str(query_ref)
    sources = json_array(json_object(result.metadata.coverage).get("source_location_refs"))
    return str(sources[0]) if sources else ""

###############################################################################
def requirement_for_location(state: AgentRunState, location_ref: str) -> TargetRequirement | None:
    """Return the goal's per-target scope for a location reference, if any."""

    goal = state.goal
    if goal is None or not goal.target_requirements or not location_ref:
        return None
    names = [
        (str(key), location.label)
        for key, location in state.location_refs.items()
        if location_ref_matches(location_ref, str(key), location.label)
    ] or [(location_ref, None)]
    return next(
        (
            requirement
            for requirement in goal.target_requirements
            if any(location_ref_matches(requirement.target_ref, key, label) for key, label in names)
        ),
        None,
    )

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
        sources = [str(item) for item in json_array(coverage.get("source_location_refs"))]
        if sources and state.goal is not None and state.goal.target_ids and not any(
            location_ref_matches(str(target), source, source)
            for target in state.goal.target_ids
            for source in sources
        ) and not {normalize_target_key(source) for source in sources}.intersection(
            normalize_target_key(key) for key in follow_up_location_keys(state)
        ):
            # Evidence derived from another place never covers this goal.
            relevant = False
            spatial = False
        if contract and contract.temporal_scope_required:
            temporal = coverage.get("temporal_scope_satisfied")
            if not isinstance(temporal, bool):
                temporal = None
            scope = state.goal.temporal_scope if state.goal else {}
            requirement = requirement_for_location(state, _result_location_ref(result))
            if requirement is not None and requirement.temporal_scope is not None:
                # A compound request judges each target against its own window.
                scope = requirement.temporal_scope.model_dump(mode="json")
            expected = scope.get("reference_time_iso") or scope.get("start_time_iso")
            observed = result.metadata.observation_time
            if expected and observed:
                try:
                    start = _parse_scope_time(str(expected))
                    actual = _parse_scope_time(observed)
                    end_value = scope.get("end_time_iso")
                    # An open-ended window ("since Monday") runs until now;
                    # only a reference instant must match exactly.
                    end = (
                        _parse_scope_time(str(end_value), inclusive_end=True)
                        if end_value
                        else start
                        if scope.get("reference_time_iso")
                        else max(start, datetime.now(UTC))
                    )
                    if scope.get("mode") == "current" and not end_value:
                        # A live reading is sampled before or after the instant
                        # the request was routed; only a stale one is wrong.
                        start, end = start - CURRENT_TOLERANCE, start + CURRENT_TOLERANCE
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
        if needs_numeric_values(state) and not analysis_unsupported(state):
            # Derived evidence inherits its parents' source; raster parents
            # cannot be transformed, so only located numeric records remain.
            results = [result for result in results if (
                result.tool_name == "execute_geospatial_capability"
                and result.metadata.result_type != "raster"
            ) or (result.tool_name == "transform_evidence" and result.metadata.capability_id)]
        assessments = [(result, CompletionEvaluator.assess_evidence(state, result)) for result in results]
        eligible = [(result, assessment) for result, assessment in assessments
                    if _is_eligible_evidence(result, assessment, analysis)]
        required = set(state.route.explicit_capability_ids if state.route else [])
        route = state.route
        data_targets = _obligation_targets(state, "data")
        per_target = (
            not required and route is not None and not analysis
            and route.location_mode == "target" and len(data_targets) >= 2
        )
        def covered(field: str) -> bool:
            if per_target:
                # Each requested place needs its own in-scope evidence; one
                # matching place must not vouch for the others.
                return all(
                    _target_has_scoped_evidence(state, target, eligible, field)
                    for target in data_targets
                )
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
            # The loop checks every requested place; the browser only needs
            # the marker layer to be part of the candidate.
            "locations_marked": any(
                instance.instance_id == PLACE_MARKERS_INSTANCE_ID
                for instance in map_session.overlay_collection.instances
            ),
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
    per_target_modes = {
        requirement.temporal_scope.mode
        for requirement in (goal.target_requirements if goal else [])
        if requirement.temporal_scope is not None and requirement.temporal_scope.mode != "none"
    }
    if goal is None or not (goal.temporal_scope or per_target_modes):
        return True
    expected_mode = str(goal.temporal_scope.get("mode") or "none")
    if expected_mode == "none" and not per_target_modes:
        return True
    # Each target's layer may carry its own mode (current vs forecast).
    expected_modes = {*per_target_modes, expected_mode} - {"none"}
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
        in expected_modes
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


_REQUIREMENT_DESCRIPTIONS = {
    "requested_transform_applied": "the requested filter or data operation could not be applied",
    "location_resolved": "the requested place was not confirmed",
    "search_area_bound": "the search area was not confirmed",
    "result_locations_derived": "no result locations were derived from the data",
    "measurement_computed": "no measurement was computed",
    "required_data_retrieved": "the requested data was not retrieved for every target",
    "evidence_inspected": "the existing evidence was not inspected",
    "capabilities_discovered": "the available data sources were not listed",
    "temporal_scope_applied": "the requested time window was not verified in the data",
    "spatial_scope_applied": "the requested area was not verified in the data",
    "map_candidate_prepared": "no map was prepared",
    "locations_marked": "the requested places were not marked on the map",
    "map_state_committed": "the map was not committed",
    "viewport_contains_results": "the map view did not contain the results",
    "final_response_ready": "the map was not confirmed",
    "render_verified": "the map was not confirmed in the browser",
}

###############################################################################
def describe_requirements(names: list[str]) -> str:
    """Name unmet completion obligations in plain language for users."""

    described = [
        _REQUIREMENT_DESCRIPTIONS.get(name, name.replace("_", " "))
        for name in dict.fromkeys(names)
    ]
    return "; ".join(described)

###############################################################################
def unmarked_route_targets(state: AgentRunState) -> list[str]:
    """Places a marking request names that the map's marker layer lacks."""

    route = state.route
    if route is None or not is_mark_locations_operation(route.operation):
        return []
    session = state.prepared_map_session or state.active_map_session
    instance = next(
        (
            item
            for item in (session.overlay_collection.instances if session else [])
            if item.instance_id == PLACE_MARKERS_INSTANCE_ID
        ),
        None,
    )
    data = json_object(instance.descriptor.get("data")) if instance else {}
    marked = [
        json_object(json_object(feature).get("properties"))
        for feature in json_array(data.get("features"))
    ]
    return [
        target
        for target in (str(ref).strip() for ref in route.target_refs)
        if target
        and not any(
            location_ref_matches(
                target,
                str(item.get("location_ref") or ""),
                str(item.get("label") or ""),
            )
            for item in marked
        )
    ]

###############################################################################
def requested_transform_unmet(state: AgentRunState) -> bool:
    """Whether the latest requested filter or transform failed.

    A later successful transform supersedes the failure; until then the
    operation the user asked for has not been applied to the evidence.
    """

    latest = next(
        (result for result in reversed(state.tool_results) if result.tool_name == "transform_evidence"),
        None,
    )
    return latest is not None and latest.status == "failed"

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
    imagery_counts = not analysis_unsupported(state)
    covered: set[str] = set()
    for result in state.tool_results:
        if result.tool_name != "execute_geospatial_capability" or not result.metadata.covered_queries:
            continue
        if analysis and imagery_counts and result.metadata.result_type == "raster":
            continue
        if _is_eligible_evidence(result, CompletionEvaluator.assess_evidence(state, result), analysis):
            covered.update(result.metadata.covered_queries)
    return [query for query in contract.data_obligations if query not in covered]


###############################################################################
def _obligation_targets(state: AgentRunState, kind: ObligationKind) -> list[str]:
    """Return the places the goal's required obligations of one kind name.

    Before a goal is compiled the validated route's targets stand in.
    """

    goal = state.goal
    if goal is None:
        return place_targets(state.route.target_refs, state) if state.route is not None else []
    return place_targets(
        dict.fromkeys(
            target
            for obligation in goal.obligations
            if obligation.required and obligation.kind == kind
            for target in obligation.target_ids
        ),
        state,
    )


###############################################################################
def uncovered_route_targets(state: AgentRunState) -> list[str]:
    """Return data-obligation targets that no data execution has covered yet.

    A comparison such as "Paris and Berlin" needs data for each place; one
    successful execution must not satisfy the whole route. Single-target and
    analysis routes keep their own coverage rules.
    """

    route = state.route
    targets = _obligation_targets(state, "data")
    if (
        route is None
        or route.analysis is not None
        or route.location_mode != "target"
        or len(targets) < 2
    ):
        return []
    # Executions name a target by any spelling the model chose; stored refs
    # are normalized keys, so compare both sides normalized.
    covered_keys: set[str] = set()
    for result in state.tool_results:
        if result.tool_name not in {"execute_geospatial_capability", "inspect_evidence", "transform_evidence"}:
            continue
        if not _is_eligible_evidence(result, CompletionEvaluator.assess_evidence(state, result), False):
            continue
        # Executions name their target in the query; inspected or derived
        # evidence (possibly from an earlier turn) carries its source targets.
        covered_keys.add(normalize_target_key(str(json_object(json_object(result.data).get("query")).get("location_ref") or "")))
        covered_keys.update(
            normalize_target_key(str(ref))
            for ref in json_array(json_object(result.metadata.coverage).get("source_location_refs"))
        )
    uncovered: list[str] = []
    for target in targets:
        matches = [
            key
            for key, location in state.location_refs.items()
            if location_ref_matches(str(target), str(key), location.label)
        ]
        # A target that never resolved cannot have been covered.
        if not matches or not covered_keys.intersection(normalize_target_key(key) for key in matches):
            uncovered.append(str(target))
    return uncovered


###############################################################################
def _target_has_scoped_evidence(
    state: AgentRunState,
    target: str,
    eligible: list[tuple[ToolResult, EvidenceAssessment]],
    field: str,
) -> bool:
    """Whether eligible evidence for this target satisfies the named scope."""

    keys = {
        normalize_target_key(key)
        for key, location in state.location_refs.items()
        if location_ref_matches(target, str(key), location.label)
    }
    for result, assessment in eligible:
        named = {
            normalize_target_key(str(json_object(json_object(result.data).get("query")).get("location_ref") or "")),
            *(
                normalize_target_key(str(ref))
                for ref in json_array(json_object(result.metadata.coverage).get("source_location_refs"))
            ),
        }
        if keys.intersection(named) and getattr(assessment, field) is True:
            return True
    return False


###############################################################################
def uncovered_map_targets(state: AgentRunState, layer_refs: set[str]) -> list[str]:
    """Return compared targets whose evidence is not among the map's layers.

    Data for every target can be retrieved and still be missing from the
    map; a comparison map must show a layer for each requested place.
    """

    route = state.route
    targets = _obligation_targets(state, "presentation")
    contract = state.completion_contract
    if (
        route is None
        # Without required evidence no target has data a layer could carry
        # (a framing or layer-removal map).
        or contract is None
        or not contract.evidence_required
        or route.analysis is not None
        or route.location_mode != "target"
        or route.presentation not in {"map", "both"}
        or len(targets) < 2
    ):
        return []
    shown: set[str] = set()
    for result in state.tool_results:
        if not set(result.evidence_refs).intersection(layer_refs):
            continue
        shown.add(normalize_target_key(str(json_object(json_object(result.data).get("query")).get("location_ref") or "")))
        shown.update(
            normalize_target_key(str(ref))
            for ref in json_array(json_object(result.metadata.coverage).get("source_location_refs"))
        )
    uncovered: list[str] = []
    for target in targets:
        matches = [
            key
            for key, location in state.location_refs.items()
            if location_ref_matches(str(target), str(key), location.label)
        ]
        if matches and not shown.intersection(normalize_target_key(key) for key in matches):
            uncovered.append(str(target))
    return uncovered


_POSITION_KEYS = frozenset({"latitude", "longitude", "lat", "lon", "lng"})
_COORDINATE_KEYS = _POSITION_KEYS | {"id", "elevation"}
_MAX_EVIDENCE_NUMBERS = 400
# Record fields that name what a statistic's extreme record is.
_RECORD_LABEL_KEYS = ("name", "title", "place", "label", "id")

###############################################################################
def _numeric_leaves(value: object, key: str = "", depth: int = 0) -> list[tuple[str, float]]:
    """Collect the numeric values of a tool payload, with the key that names them."""

    if depth > 6 or isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [] if key in _COORDINATE_KEYS else [(key, float(value))]
    leaves: list[tuple[str, float]] = []
    if isinstance(value, dict):
        for name, item in json_object(value).items():
            leaves.extend(_numeric_leaves(item, str(name), depth + 1))
    elif isinstance(value, list):
        for item in json_array(value)[:200]:
            leaves.extend(_numeric_leaves(item, key, depth + 1))
    return leaves

###############################################################################
def _position_leaves(value: object, key: str = "", depth: int = 0) -> list[float]:
    """Collect the latitude and longitude values the records of a payload carry."""

    if depth > 6 or isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)] if key in _POSITION_KEYS else []
    leaves: list[float] = []
    if isinstance(value, dict):
        for name, item in json_object(value).items():
            leaves.extend(_position_leaves(item, str(name), depth + 1))
    elif isinstance(value, list):
        for item in json_array(value)[:200]:
            leaves.extend(_position_leaves(item, key, depth + 1))
    return leaves

###############################################################################
def evidence_coordinates(state: AgentRunState) -> list[float]:
    """Latitudes and longitudes of the records the run's and earlier turns' evidence carries.

    An answer may cite the position of a record it inspected or derived (the
    strongest event); resolved places are checked separately.
    """

    values: list[float] = []
    for result in state.tool_results:
        if result.status != "failed" and result.tool_name != "resolve_geospatial_location":
            values.extend(_position_leaves(result.data))
    for item in state.relevant_tool_outcomes:
        if item.get("evidence_id"):
            values.extend(_position_leaves(item.get("summary")))
    return values[:_MAX_EVIDENCE_NUMBERS]

###############################################################################
def evidence_numbers(state: AgentRunState) -> list[float]:
    """Every number the run's evidence carries, for checking cited values."""

    numbers: list[float] = []
    for result in state.tool_results:
        if result.status == "failed" or result.tool_name == "resolve_geospatial_location":
            continue
        numbers.extend(value for _, value in _numeric_leaves(result.data))
        if len(numbers) >= _MAX_EVIDENCE_NUMBERS:
            break
    return numbers[:_MAX_EVIDENCE_NUMBERS]

###############################################################################
def _time_zone_names(value: object) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, item in json_object(value).items():
            if key == "timezone" and isinstance(item, str):
                found.add(item)
            else:
                found |= _time_zone_names(item)
        return found
    if isinstance(value, list):
        return {name for item in json_array(value) for name in _time_zone_names(item)}
    return set()


###############################################################################
def evidence_utc_offsets(state: AgentRunState) -> set[float]:
    """Current UTC offsets, in seconds, of the time zones the run's evidence names."""

    now = datetime.now(UTC)
    offsets: set[float] = set()
    for result in state.tool_results:
        for name in _time_zone_names(result.data):
            try:
                offset = now.astimezone(ZoneInfo(name)).utcoffset()
            except (ValueError, ZoneInfoNotFoundError):
                continue
            if offset is not None:
                offsets.add(offset.total_seconds())
    return offsets


###############################################################################
def prior_evidence_numbers(state: AgentRunState) -> list[float]:
    """Numbers of the earlier turns' evidence summaries this run's context shows."""

    numbers = [
        value
        for item in state.relevant_tool_outcomes
        if item.get("evidence_id")
        for _, value in _numeric_leaves(item.get("summary"))
    ]
    return numbers[:_MAX_EVIDENCE_NUMBERS]

###############################################################################
def key_names_variable(key: str, variable: str | None) -> bool:
    """Whether a payload key names the variable.

    "mag" names "magnitude"; "temperature_2m" names "current temperature".
    """

    leaf = key.rsplit(".", 1)[-1].casefold()
    asked = (variable or "").casefold()
    name = re.sub(r"[^a-z0-9]", "", leaf)
    wanted = re.sub(r"[^a-z0-9]", "", asked)
    if len(name) >= 3 and wanted and (name in wanted or wanted in name):
        return True
    return bool(set(re.findall(r"[a-z]{3,}", leaf)) & set(re.findall(r"[a-z]{3,}", asked)))

###############################################################################
def _statistic_values(statistics: dict[str, Any], variable: str | None, limit: int) -> list[str]:
    """Extremes of the summarised fields, with the record holding the maximum."""

    keys = [key for key in statistics if key_names_variable(key, variable)] or list(statistics)
    values: list[str] = []
    for key in keys[:limit]:
        stat = json_object(statistics[key])
        holder = json_object(stat.get("argmax"))
        label = next((str(holder[name]) for name in _RECORD_LABEL_KEYS if holder.get(name)), "")
        values.append(
            f"{key.replace('_', ' ')} max {stat.get('max')}"
            + (f" ({label})" if label else "")
            + f", min {stat.get('min')}"
        )
    return values

###############################################################################
def _leading_values(result: ToolResult, limit: int = 3, variable: str | None = None) -> list[str]:
    """Name the first numeric facts of a result, with units where known.

    Facts naming the requested ``variable`` come first.
    """

    data = json_object(result.data)
    if result.tool_name == "inspect_evidence":
        inspected = json_object(data.get("result"))
        if "statistics" in inspected:
            return _statistic_values(json_object(inspected["statistics"]), variable, limit)
        records = json_array(inspected.get("records"))
        source = json_object(records[0]) if records else {}
    else:
        preview = json_array(data.get("preview"))
        source = json_object(preview[0]) if preview else data
    seen: set[str] = set()
    named: list[tuple[str, float]] = []
    for name, value in _numeric_leaves(source):
        if name and name not in seen and not name.endswith("_count"):
            seen.add(name)
            named.append((name, value))
    named.sort(key=lambda item: not key_names_variable(item[0], variable))
    return [
        f"{name.replace('_', ' ')} {value:g}{(' ' + unit) if (unit := result.metadata.units.get(name, '')) else ''}"
        for name, value in named[:limit]
    ]

###############################################################################
def _value_numbers(result: ToolResult, variable: str | None) -> list[float]:
    """Numbers of a result that an answer about ``variable`` may cite."""

    leaves = [
        (key, value) for key, value in _numeric_leaves(result.data)
        if key != "count" and not key.endswith("_count")
    ]
    named = [value for key, value in leaves if key_names_variable(key, variable)]
    return (named or [value for _, value in leaves])[:_MAX_EVIDENCE_NUMBERS]

###############################################################################
def _source_figures(result: ToolResult, variable: str | None) -> tuple[list[str], list[list[float]]]:
    """Each source's figure in a record set combined from several evidence refs.

    Returns the labelled values and the figures per source. A comparison over
    earlier turns has no execution in this run: only the combined records say
    which figure belongs to which place. Fewer than two sources compare nothing.
    """

    values: list[str] = []
    numbers: list[float] = []
    unit = ""
    groups: dict[str, list[float]] = {}
    for item in json_array(json_object(result.data).get("preview")):
        record = json_object(item)
        fields = json_object(record.get("properties")) or record
        source = str(fields.get("source_ref") or "")
        named = [
            (key, float(value)) for key, value in fields.items()
            if key_names_variable(key, variable)
            and isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if not source or not named:
            continue
        key, number = min(named, key=lambda pair: len(pair[0]))
        groups.setdefault(source, []).extend(value for _, value in named)
        numbers.append(number)
        unit = f" {result.metadata.units[key]}" if key in result.metadata.units else ""
        label = next(
            (str(fields[name]) for name in ("place_label", "source_place", *_RECORD_LABEL_KEYS) if fields.get(name)),
            source,
        )
        values.append(f"{label}: {key.replace('_', ' ')} {number:g}{unit}")
    if len(groups) < 2:
        return [], []
    if len(numbers) == 2:
        values.append(f"difference {abs(numbers[0] - numbers[1]):g}{unit}")
    return values, list(groups.values())

###############################################################################
def _scoped_data_result(state: AgentRunState, target: str) -> ToolResult | None:
    """The latest data result retrieved for ``target`` itself, if any."""

    return next((
        result for result in reversed(state.tool_results)
        if result.tool_name == "execute_geospatial_capability"
        and result.status in {"success", "partial"}
        and (named := _result_location_ref(result))
        and location_ref_matches(target, named, named)
    ), None)

###############################################################################
def _map_layer_refs(session: MapSession) -> set[str]:
    return {
        str(instance.descriptor.get("evidence_ref"))
        for instance in session.overlay_collection.instances
        if instance.descriptor.get("evidence_ref")
    }

###############################################################################
def _annotated_refs(session: MapSession) -> set[str]:
    """Places whose marker carries a value label, which is data on the map."""

    return {
        str(properties.get("location_ref"))
        for instance in session.overlay_collection.instances
        if instance.instance_id == PLACE_MARKERS_INSTANCE_ID and instance.visible
        for feature in json_array(json_object(instance.descriptor.get("data")).get("features"))
        if (properties := json_object(json_object(feature).get("properties"))).get("annotation")
    }

###############################################################################
def _bare_value_markers(session: MapSession) -> bool:
    """Whether the map's only visible data is place markers that carry no value."""

    visible = [instance for instance in session.overlay_collection.instances if instance.visible]
    if not visible or any(instance.instance_id != PLACE_MARKERS_INSTANCE_ID for instance in visible):
        return False
    features = json_array(json_object(visible[0].descriptor.get("data")).get("features"))
    return not features or any(
        not json_object(json_object(feature).get("properties")).get("annotation")
        for feature in features
    )

###############################################################################
def data_verified_empty(state: AgentRunState) -> bool:
    """Whether every requested data query completed and found nothing.

    A completed empty query is the answer; there is nothing to map, rank or
    compare, so the run should say so instead of trying to present it.
    """

    executed = [
        result for result in state.tool_results
        if result.tool_name == "execute_geospatial_capability" and result.status != "failed"
    ]
    return (
        bool(executed)
        and all(result.status == "valid_empty" for result in executed)
        and CompletionEvaluator.data_checks(state)["required_data_retrieved"]
    )

###############################################################################
def presentation_contract(state: AgentRunState, session: MapSession) -> PresentationContract | None:
    """Build the presentation contract of a map candidate from the goal.

    Returns ``None`` when the goal has no presentation obligation. Findings
    are the verdicts the server can already give about the candidate; the
    browser viewport is checked against ``targets`` at acknowledgment.
    """

    goal = state.goal
    obligation = next(
        (item for item in (goal.obligations if goal else []) if item.kind == "presentation" and item.required),
        None,
    )
    if goal is None or obligation is None:
        return None
    route = state.route
    edits_current_map = route is not None and route.primary_domain is CapabilityDomain.MAP_STATE
    targets: list[ContractTarget] = []
    for ref in [] if edits_current_map else obligation.target_ids:
        match = next(
            (
                (str(key), location)
                for key, location in state.location_refs.items()
                if location_ref_matches(ref, str(key), location.label)
            ),
            None,
        )
        if match is not None:
            targets.append(ContractTarget(
                ref=match[0], label=match[1].label, latitude=match[1].latitude,
                longitude=match[1].longitude, location_type=match[1].location_type,
                bbox=match[1].bbox,
            ))
    findings: list[str] = []
    layer_refs = _map_layer_refs(session)
    labelled = _annotated_refs(session)
    missing = [
        target for target in uncovered_map_targets(state, layer_refs)
        if not any(location_ref_matches(target, ref, ref) for ref in labelled)
    ]
    if missing:
        findings.append("no map layer carries the data for " + ", ".join(missing))
    contract = state.completion_contract
    if contract is not None and contract.temporal_scope_required and any(
        set(result.evidence_refs).intersection(layer_refs)
        and CompletionEvaluator.assess_evidence(state, result).temporal_scope_satisfied is False
        for result in state.tool_results
    ):
        findings.append("a map layer is not from the requested time window")
    if requested_transform_unmet(state):
        findings.append("the requested filter or transform is not applied to the map data")
    if obligation.variable and _bare_value_markers(session):
        findings.append(
            f"the map shows places without the {obligation.variable} values; "
            "label the markers with the values or map the data layer"
        )
    return PresentationContract(targets=targets, findings=findings)

###############################################################################
def layer_edit_count(state: AgentRunState) -> int:
    """Layers this run removed, hid or re-opacified, from the map-state diff."""

    before = state.active_map_session
    after = state.prepared_map_session
    if after is None:
        # After the render commits, the active map is the edited one: the
        # diff survives only in the map-plan result that prepared it.
        prepared = next(
            (
                item.data
                for item in reversed(state.tool_results)
                if item.tool_name == "apply_map_plan" and item.status == "success"
                and isinstance(item.data, dict) and "layer_edits" in item.data
            ),
            None,
        )
        edits = prepared.get("layer_edits") if prepared is not None else 0
        return edits if isinstance(edits, int) else 0
    if before is None:
        return 0
    kept = {item.instance_id: item for item in after.overlay_collection.instances}
    return sum(
        1
        for item in before.overlay_collection.instances
        if (current := kept.get(item.instance_id)) is None
        or (current.visible, current.opacity) != (item.visible, item.opacity)
    )

###############################################################################
def _map_state(state: AgentRunState) -> MapState:
    if state.render_verified:
        return "rendered"
    if state.render_retry_exhausted or (
        state.render_observations and state.render_observations[-1].status == "failed"
    ):
        return "failed"
    return "none"

###############################################################################
def map_layer_counts(state: AgentRunState, session: MapSession) -> dict[str, tuple[int, int]]:
    """(shown, total) per visible evidence layer instance: drawn features vs source records."""

    counts: dict[str, tuple[int, int]] = {}
    for instance in session.overlay_collection.instances:
        ref = str(instance.descriptor.get("evidence_ref") or "")
        features = json_object(instance.descriptor.get("data")).get("features")
        if not instance.visible or not ref or not isinstance(features, list):
            continue
        # The newest result that counted this evidence; map-plan results also
        # carry the ref but no count.
        total = next(
            (
                value
                for item in reversed(state.tool_results)
                if ref in item.evidence_refs
                for key in ("truncated_from", "feature_count", "record_count")
                if isinstance(value := json_object(item.data).get(key), int) and value > 0
            ),
            0,
        )
        if total:
            counts[instance.instance_id] = (len(json_array(features)), total)
    return counts

###############################################################################
def _truncations(state: AgentRunState) -> list[tuple[int, int]]:
    session = state.prepared_map_session or state.active_map_session
    if session is None:
        return []
    return [(shown, total) for shown, total in map_layer_counts(state, session).values() if shown < total][-8:]

###############################################################################
def _obligation_result(state: AgentRunState, kind: ObligationKind, target: str | None) -> ToolResult | None:
    tools = (
        {"execute_geospatial_capability"}
        if kind == "data"
        else {"transform_evidence", "measure_geospatial", "inspect_evidence"}
    )
    candidates = [
        result for result in state.tool_results
        if result.tool_name in tools and result.status in {"success", "partial", "valid_empty"}
    ]
    if kind == "data" and target:
        scoped = [
            result for result in candidates
            if (named := _result_location_ref(result)) and location_ref_matches(target, named, named)
        ]
        candidates = scoped or candidates
    return candidates[-1] if candidates else None

###############################################################################
def _identified_place(state: AgentRunState, target: str) -> tuple[str, str] | None:
    """Return (full name, short name) of the place a target was identified as.

    A coordinate target is identified only by its reverse geocode; a named
    target by its own resolution.
    """

    for key, location in state.location_refs.items():
        if not location_ref_matches(target, str(key), location.label):
            continue
        if location.location_type == "coordinates":
            full = location.reverse_geocoded_name()
            return (full, full.split(",")[0].strip()) if full else None
        return location.label, location.label.split(",")[0].strip()
    return None

###############################################################################
def _identification_places(
    state: AgentRunState, targets: list[str]
) -> list[tuple[str, str] | None]:
    """Return the places an identification obligation asks to name.

    One naming no target asks about the coordinates the run was given, like
    the reverse geocode it triggers: the latest coordinates the run identified.
    """

    if targets:
        return [_identified_place(state, target) for target in targets]
    names = [
        name
        for location in state.location_refs.values()
        if location.location_type == "coordinates" and (name := location.reverse_geocoded_name())
    ]
    return [(names[-1], names[-1].split(",")[0].strip())] if names else []

###############################################################################
def _obligation_label(obligation: RequestObligation) -> str:
    places = ", ".join(obligation.target_ids)
    if obligation.kind == "presentation":
        return "the requested map"
    if obligation.kind == "location":
        return f"the place {places}" if places else "the requested place"
    if obligation.kind == "identification":
        return f"the name of the place at {places}" if places else "the name of the requested place"
    if obligation.kind == "data":
        subject = f"{obligation.variable} data" if obligation.variable else "the requested data"
        return f"{subject} for {places}" if places else subject
    return f"the requested {obligation.id.split(':')[-1].replace('_', ' ')}"

###############################################################################
def _substitutions(state: AgentRunState) -> list[tuple[str, str, str]]:
    """Covering sources that replaced a rejected one and then ran."""

    executed = {
        result.metadata.capability_id for result in state.tool_results
        if result.tool_name == "execute_geospatial_capability" and result.status == "success"
    }
    substitutions: list[tuple[str, str, str]] = []
    for result in state.tool_results:
        record = json_object(json_object(result.data).get("substitution")) if result.status == "failed" else {}
        if not record.get("alternative_id") or record["alternative_id"] not in executed:
            continue
        item = (
            str(record.get("rejected_name")), str(record.get("coverage") or ""), str(record.get("alternative_name"))
        )
        if item not in substitutions:
            substitutions.append(item)
    return substitutions[:4]

###############################################################################
def build_completion_summary(state: AgentRunState, checks: dict[str, bool]) -> CompletionSummary:
    """Turn the run's verified facts into per-obligation outcomes.

    ``checks`` are the loop's requirement verdicts. A render observation only
    decides presentation obligations; data and analysis obligations read
    their own requirements and never a browser acknowledgment.
    """

    goal = state.goal
    contract = state.completion_contract
    requirements = list(contract.requirements) if contract is not None else []
    map_state = _map_state(state)
    findings: list[str] = []
    if map_state == "failed":
        failure = next((item for item in state.render_observations if item.status == "failed"), None)
        if failure is not None and failure.failure_stage == "presentation_contract" and failure.failure_summary:
            findings = [failure.failure_summary]
    uncovered = uncovered_route_targets(state)
    outcomes: list[ObligationOutcome] = []
    # An answer-mode route has no tools to satisfy an obligation with and skips
    # the pre-tool obligation check, so what its model declared decides nothing.
    for obligation in (goal.obligations if goal is not None and goal.task_mode != "answer" else []):
        if not obligation.required:
            continue
        evidence_ref: str | None = None
        values: list[str] = []
        must_name: list[str] = []
        cite_groups: list[list[float]] = []
        label = _obligation_label(obligation)
        status: ObligationStatus
        if obligation.kind == "presentation":
            status = "met" if map_state == "rendered" else "failed" if map_state == "failed" else "unmet"
        elif obligation.kind == "identification":
            # Met only by resolution evidence that names every target place;
            # the answer must then name it too.
            place_ids = obligation.target_ids or (goal.target_ids if goal is not None else [])
            places = _identification_places(state, place_ids)
            named = [item for item in places if item is not None]
            status = "met" if named and len(named) == len(places) else "unmet"
            if not place_ids and any(
                result.status == "success" and result.evidence_refs for result in state.tool_results
            ):
                # "Which one was strongest?" identifies a record, not a place:
                # the evidence holding that record delivers it.
                status = "met"
            if named and status == "met":
                values = [full for full, _ in named][:8]
                # Spellings that name the (first) identified place.
                must_name = list(dict.fromkeys([named[0][1], named[0][0]]))
        else:
            requirement = obligation_requirement(obligation.kind, requirements)
            target = obligation.target_ids[0] if obligation.target_ids else None
            if requirement is None and obligation.kind == "location":
                # Always routed, even on a contract that resolves nothing (a
                # recenter on a known place): the place is delivered once known.
                known = bool(obligation.target_ids) and all(
                    any(location_ref_matches(target, str(key), item.label) for key, item in state.location_refs.items())
                    for target in obligation.target_ids
                )
                status = "met" if known else "unmet"
            elif requirement is None:
                status = "unmet"
            elif obligation.kind == "analysis" and analysis_unsupported(state):
                status = "unsupported"
            elif obligation.kind in {"data", "analysis"} and requested_transform_unmet(state):
                status = "failed"
            elif obligation.kind == "data" and target is not None and any(
                location_ref_matches(target, name, name) for name in state.failed_data_targets
            ):
                status = "failed"
            else:
                target_uncovered = obligation.kind == "data" and target is not None and any(
                    location_ref_matches(target, name, name) for name in uncovered
                )
                status = "met" if checks.get(requirement, False) and not target_uncovered else "unmet"
            result = None if obligation.kind == "location" else _obligation_result(state, obligation.kind, target)
            # Retrieved figures stay deliverable when only a later analysis
            # step failed.
            if result is not None and (status == "met" or (obligation.kind == "data" and status == "failed")):
                evidence_ref = result.evidence_refs[0] if result.evidence_refs else None
                values = _leading_values(result, variable=obligation.variable)
            if obligation.kind == "location" and status == "met" and is_text_location_lookup(state.route):
                located = next((
                    item for key, item in state.location_refs.items()
                    if target is not None and location_ref_matches(target, str(key), item.label)
                ), None)
                if located is not None:
                    # The coordinates are the requested result, so the answer
                    # must cite them; either sign, for "9.14 W".
                    label = (located.label or label)[:200]
                    values = [f"latitude {located.latitude:.5f}, longitude {located.longitude:.5f}"]
                    cite_groups = [
                        [located.latitude, -located.latitude],
                        [located.longitude, -located.longitude],
                    ]
            if obligation.kind == "analysis" and status == "met":
                # A comparison cites each target's own figure (or their
                # difference); any other analysis cites its result.
                figures, cite_groups = (
                    _source_figures(result, obligation.variable) if result is not None else ([], [])
                )
                if figures:
                    values = figures
                else:
                    scoped = [_scoped_data_result(state, item) for item in obligation.target_ids]
                    sources = (
                        [item for item in scoped if item is not None]
                        if len(scoped) > 1
                        else [result] if result is not None else []
                    )
                    cite_groups = [_value_numbers(item, obligation.variable) for item in sources]
        outcomes.append(ObligationOutcome(
            obligation_id=obligation.id, kind=obligation.kind, status=status,
            label=label,
            evidence_ref=evidence_ref, values=values, answer_must_name=must_name,
            cite_groups=cite_groups,
        ))
    return CompletionSummary(
        obligations=outcomes, map_state=map_state,
        presentation_findings=findings, substitutions=_substitutions(state),
        truncations=_truncations(state),
    )

###############################################################################
def ledger_outcomes(
    state: AgentRunState, summary: CompletionSummary, *, now: datetime
) -> list[ConversationTask]:
    """Conversation-ledger entries for what this run verifiably did.

    Only the completion summary decides status: a met obligation completes,
    a failed one fails, a map prepared and awaiting the browser stays in
    progress, and any other unmet one is blocked with the run's stop reason,
    so a follow-up can see unfinished work.  Evidence and capability come from
    the run's own tool results; a reused result keeps its original fetch
    time, so reuse never extends evidence freshness.
    """

    goal = state.goal
    if goal is None or state.typed_task_state().status in {"cancelled", "superseded"}:
        return []
    verdicts = {item.obligation_id: item for item in summary.obligations}
    required = [item for item in goal.obligations if item.required]
    data_ids = [item.id for item in required if item.kind in {"data", "analysis"}]
    shown = state.active_map_session if state.render_verified else state.prepared_map_session
    tasks: list[ConversationTask] = []
    for obligation in required:
        verdict = verdicts.get(obligation.id)
        if verdict is None:
            continue
        status: ConversationTaskStatus
        reason: str | None = None
        if verdict.status == "met":
            status = "completed"
        elif verdict.status == "failed":
            status = "failed"
            reason = (
                "requested_transform_unmet"
                if obligation.kind in {"data", "analysis"} and requested_transform_unmet(state)
                else "provider_failed"
            )
        elif obligation.kind == "presentation" and state.prepared_map_session is not None:
            status = "in_progress"
        elif verdict.status == "unsupported":
            status, reason = "blocked", "evidence_unsupported"
        else:
            status = "blocked"
            stop = state.termination_reason
            reason = stop[:80] if stop and stop != "goal_satisfied" else "unmet"
        target = obligation.target_ids[0] if obligation.target_ids else None
        result = (
            _obligation_result(state, obligation.kind, target)
            if obligation.kind in {"data", "analysis"}
            else None
        )
        if obligation.kind == "location":
            dependencies: list[str] = []
        elif obligation.kind in {"data", "identification"}:
            dependencies = [
                item.id
                for item in required
                if item.kind == "location"
                and any(location_ref_matches(ref, other, other) for ref in item.target_ids for other in obligation.target_ids)
            ]
        elif obligation.kind == "analysis":
            dependencies = [item for item in data_ids if item != obligation.id]
        else:
            dependencies = list(data_ids)
        completed_at: datetime | None = None
        if status == "completed":
            fetched = result.metadata.fetched_at if result is not None else None
            completed_at = _parse_scope_time(fetched) if fetched else now
        tasks.append(ConversationTask(
            task_id=obligation.id,
            description=_obligation_label(obligation)[:300],
            kind=obligation.kind,
            status=status,
            reason=reason,
            dependencies=dependencies[:16],
            target_ids=list(obligation.target_ids),
            capability_id=result.metadata.capability_id if result is not None else None,
            variable=obligation.variable,
            temporal_scope=obligation.temporal_scope,
            filters=dict(goal.filters),
            evidence_refs=list(result.evidence_refs[:8]) if result is not None and status == "completed" else [],
            map_revision=(
                map_fingerprint(shown) if obligation.kind == "presentation" and shown is not None else None
            ),
            source_request_id=state.request_id,
            completed_at=completed_at,
        ))
    return tasks

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
    "build_completion_summary",
    "data_verified_empty",
    "evidence_numbers",
    "evidence_utc_offsets",
    "prior_evidence_numbers",
    "presentation_contract",
    "describe_requirements",
    "RASTER_ONLY_CODE",
    "analysis_unsupported",
    "imagery_only_note",
    "key_names_variable",
    "ledger_outcomes",
    "needs_numeric_values",
    "requested_transform_unmet",
    "follow_up_location_keys",
    "uncovered_map_targets",
    "uncovered_data_obligations",
    "uncovered_route_targets",
    "evidence_coordinates",
]
