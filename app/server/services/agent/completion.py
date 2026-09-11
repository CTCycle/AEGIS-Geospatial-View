"""Deterministic completion checks for data and map presentation."""

from __future__ import annotations

from typing import Any, cast

from server.domain.agent.interpretation import (
    CanonicalRequestInterpretation,
    CompletionRequirement,
)
from server.contracts.geospatial import MapSession
from server.domain.agent.evidence import AgentStopEvaluation


REQUIRED_COMPLETION_NAMES = (
    "location_resolved",
    "required_data_retrieved",
    "spatial_filter_applied",
    "temporal_filter_applied",
    "renderable_geometry_created",
    "map_state_committed",
    "viewport_contains_results",
    "final_response_ready",
)

###############################################################################
class CompletionEvaluator:
    """Keep task completion independent of provider or model wording."""

    # -------------------------------------------------------------------------
    @staticmethod
    def evaluate_proposed_stop(
        *,
        canonical_request: CanonicalRequestInterpretation | None,
        presentation_required: bool,
        map_prepared: bool,
        evidence_refs: list[str] | None,
        available_tools: list[str],
        clarification_required: bool = False,
        provider_error: bool = False,
    ) -> AgentStopEvaluation:
        """Evaluate a no-tool model response against durable requirements."""

        if clarification_required:
            return AgentStopEvaluation(
                proposed=True,
                satisfied=False,
                reason="clarification_required",
                pending_requirements=["user_input"],
                useful_tools=[],
            )
        if provider_error:
            return AgentStopEvaluation(
                proposed=True,
                satisfied=False,
                reason="provider_error",
                pending_requirements=[],
                useful_tools=[],
            )
        if presentation_required:
            if map_prepared:
                return AgentStopEvaluation(
                    proposed=True,
                    satisfied=False,
                    reason="awaiting_render",
                    pending_requirements=["map_state_committed", "viewport_contains_results"],
                    useful_tools=[],
                )
            return AgentStopEvaluation(
                proposed=True,
                satisfied=False,
                reason="insufficient_evidence" if not available_tools else "no_progress",
                pending_requirements=["prepare_geospatial_map"],
                useful_tools=available_tools,
            )
        required = [
            item.name
            for item in (canonical_request.completion_requirements if canonical_request else [])
            if item.required and item.status not in {"satisfied", "not_applicable"}
        ]
        if required and not evidence_refs:
            return AgentStopEvaluation(
                proposed=True,
                satisfied=False,
                reason="insufficient_evidence" if not available_tools else "no_progress",
                pending_requirements=required,
                useful_tools=available_tools,
            )
        return AgentStopEvaluation(
            proposed=True,
            satisfied=True,
            reason="goal_satisfied",
            pending_requirements=[],
            useful_tools=[],
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def candidate_requirements(
        canonical_request: CanonicalRequestInterpretation | None,
        map_session: MapSession,
    ) -> list[CompletionRequirement]:
        existing = (
            list(canonical_request.completion_requirements)
            if canonical_request is not None
            else []
        )
        by_name = {item.name: item for item in existing}
        target_id = (
            canonical_request.primary_target.target_id
            if canonical_request is not None and canonical_request.primary_target
            else None
        )
        # A map candidate proves only preparation. Commit, viewport, and final
        # response remain pending until the browser acknowledgment arrives.
        failure_codes: dict[str, str] = {}
        required_data_retrieved = CompletionEvaluator._data_retrieved(
            canonical_request, map_session
        )
        if not required_data_retrieved:
            failure_codes["required_data_retrieved"] = "required_data_unavailable"
        spatial_filter_applied = CompletionEvaluator._spatial_filter_applied(
            canonical_request, map_session
        )
        if not spatial_filter_applied:
            failure_codes["spatial_filter_applied"] = "spatial_scope_mismatch"
        temporal_filter_applied = CompletionEvaluator._temporal_filter_applied(
            canonical_request, map_session
        )
        if not temporal_filter_applied:
            failure_codes["temporal_filter_applied"] = "temporal_scope_mismatch"
        values = {
            "location_resolved": bool(map_session.resolved_location),
            "required_data_retrieved": required_data_retrieved,
            "spatial_filter_applied": spatial_filter_applied,
            "temporal_filter_applied": temporal_filter_applied,
            "renderable_geometry_created": CompletionEvaluator._has_renderable_output(
                map_session
            ),
            "map_state_committed": False,
            "viewport_contains_results": False,
            "final_response_ready": False,
        }
        requirements: list[CompletionRequirement] = []
        names: list[str] = list(REQUIRED_COMPLETION_NAMES)
        for item in existing:
            if item.name not in names:
                names.append(item.name)
        for name in names:
            source = by_name.get(name)
            requirements.append(
                CompletionRequirement(
                    name=name,
                    required=source.required if source is not None else True,
                    status=(
                        "satisfied"
                        if values.get(name, False)
                        else "failed"
                        if name in failure_codes
                        else "pending"
                    ),
                    target_id=source.target_id if source is not None else target_id,
                    evidence_ref=f"map_session:{map_session.session_id}",
                    failure_code=failure_codes.get(name),
                )
            )
        return requirements

    # -------------------------------------------------------------------------
    @staticmethod
    def _data_retrieved(
        canonical_request: CanonicalRequestInterpretation | None,
        map_session: MapSession,
    ) -> bool:
        """Reject explicit provider failures without rejecting valid empties."""

        if canonical_request is None:
            return True
        # ``geospatial_data_retrieval`` is also the normalized action used for
        # a location-only viewport request.  It is not, by itself, evidence
        # that an overlay/provider dataset was requested; the basemap and
        # resolved viewport are sufficient for that presentation.  Explicit
        # domains or data-layer operations still require a validated result.
        data_requested = bool(canonical_request.data_domains) or any(
            operation
            in {
                "search",
                "filter",
                "overlay",
                "inspect",
                "calculate",
                "data_layer_query",
                "dataset_display",
            }
            for operation in canonical_request.operations
        )
        if not data_requested:
            return True
        instances = map_session.overlay_collection.instances
        if not instances:
            return False
        failure_statuses = {"unavailable", "invalid", "error", "failed"}
        for instance in instances:
            descriptor = instance.descriptor
            status = str(
                descriptor.get("result_status")
                or descriptor.get("resultStatus")
                or ""
            ).casefold()
            render_status = str(
                descriptor.get("render_status")
                or descriptor.get("renderStatus")
                or ""
            ).casefold()
            if status in failure_statuses or render_status in failure_statuses:
                return False
        return True

    # -------------------------------------------------------------------------
    @staticmethod
    def _spatial_filter_applied(
        canonical_request: CanonicalRequestInterpretation | None,
        map_session: MapSession,
    ) -> bool:
        constraints = canonical_request.spatial_constraints if canonical_request else []
        if not constraints:
            return True
        expected = {constraint.analysis_scope for constraint in constraints}
        strict_evidence = any(
            constraint.provenance in {"explicit", "viewport"}
            or constraint.analysis_scope != "bbox"
            for constraint in constraints
        )
        for instance in map_session.overlay_collection.instances:
            descriptor = instance.descriptor
            declared = descriptor.get("analysis_scope") or descriptor.get("scope_kind")
            if declared is not None and str(declared) not in expected:
                return False
            if strict_evidence and declared is None:
                return False
        return True

    # -------------------------------------------------------------------------
    @staticmethod
    def _temporal_filter_applied(
        canonical_request: CanonicalRequestInterpretation | None,
        map_session: MapSession,
    ) -> bool:
        temporal = canonical_request.temporal_constraints if canonical_request else None
        if temporal is None or (
            temporal.mode == "none"
            and temporal.start_time_iso is None
            and temporal.end_time_iso is None
        ):
            return True
        for instance in map_session.overlay_collection.instances:
            descriptor = instance.descriptor
            declared_mode = descriptor.get("temporal_mode") or descriptor.get("time_mode")
            if declared_mode is None:
                return False
            if str(declared_mode) != temporal.mode:
                return False
            for key, expected in (
                ("start_time_iso", temporal.start_time_iso),
                ("end_time_iso", temporal.end_time_iso),
            ):
                actual = descriptor.get(key)
                if expected is not None:
                    if actual is None or str(actual) != expected:
                        return False
        return True

    # -------------------------------------------------------------------------
    @staticmethod
    def acknowledge_requirements(
        requirements: list[dict[str, Any]],
        acknowledgment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        checks = cast(dict[str, Any], acknowledgment.get("checks")) if isinstance(
            acknowledgment.get("checks"), dict
        ) else {}
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
