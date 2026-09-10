"""Canonical typed map-plan application boundary."""

from __future__ import annotations

import time
from typing import Any, Protocol

from server.domain.agent.capability_route import AgentState
from server.domain.agent.evidence import AgentEvidenceEnvelope
from server.domain.agent.map_plan import AddEvidenceLayerAction, MapPlan
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.services.agent.capability_execution import ToolExecutionContext
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.map_session_builder import (
    MapPlanBuildError,
    MapSessionBuilder,
)


###############################################################################
class EvidenceReader(Protocol):
    def get_summary(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> Any: ...


###############################################################################
class MapPlanService:
    TOOL_NAME = "apply_map_plan"

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        evidence_repository: EvidenceReader | AgentEvidenceRepository | None = None,
        session_builder: MapSessionBuilder | None = None,
    ) -> None:
        self.evidence_repository = evidence_repository
        self.session_builder = session_builder or MapSessionBuilder(
            capability_registry=capability_registry
        )

    # -------------------------------------------------------------------------
    async def apply(
        self,
        plan: MapPlan,
        state: AgentState,
        context: ToolExecutionContext,
    ) -> ToolResult:
        started = time.perf_counter()
        active_session = state.active_map_session
        current_revision = (
            active_session.overlay_collection.revision if active_session else 0
        )
        if plan.expected_collection_revision != current_revision:
            return self._failure(
                context=context,
                started=started,
                error_type="state_conflict",
                code="stale_map_revision",
                message="The active map changed before this plan could be applied.",
                recovery="replan",
            )

        location = active_session.resolved_location if active_session else self._location(state)
        if location is None:
            return self._failure(
                context=context,
                started=started,
                error_type="state_conflict",
                code="missing_location",
                message="A validated location is required before preparing a map.",
                recovery="request_user_input",
            )

        try:
            evidence = self._evidence_for_plan(plan, state, context)
            candidate = await self.session_builder.build(
                location=location,
                evidence=evidence,
                active_session=active_session,
                actions=plan.actions,
            )
        except MapPlanBuildError as exc:
            return self._failure(
                context=context,
                started=started,
                error_type=(
                    "state_conflict"
                    if exc.code
                    in {
                        "missing_location",
                        "unknown_evidence",
                        "failed_evidence",
                        "unknown_layer",
                        "viewport_bounds_unavailable",
                    }
                    else "semantic_validation"
                ),
                code=exc.code,
                message=exc.message,
                recovery=(
                    "replan"
                    if exc.code in {"unknown_layer", "viewport_bounds_unavailable"}
                    else "correct_arguments"
                ),
            )
        except Exception:
            return self._failure(
                context=context,
                started=started,
                error_type="invalid_tool_output",
                code="map_candidate_invalid",
                message="The map candidate could not be built from validated inputs.",
                recovery="terminal",
            )

        state.prepared_map_session = candidate
        evidence_refs = [
            action.evidence_ref
            for action in plan.actions
            if isinstance(action, AddEvidenceLayerAction)
        ]
        summary = {
            "map_candidate_id": candidate.session_id,
            "collection_revision": candidate.overlay_collection.revision,
            "basemap_id": candidate.basemap_id,
            "overlay_count": len(candidate.overlay_collection.instances),
            "render_status": "awaiting_render",
        }
        return ToolResult(
            call_id=context.call_id,
            tool_name=self.TOOL_NAME,
            status="success",
            summary="A map candidate was prepared and is awaiting render acknowledgment.",
            data=summary,
            evidence_refs=list(dict.fromkeys(evidence_refs)),
            map_candidate_id=candidate.session_id,
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                evidence_refs=list(dict.fromkeys(evidence_refs)),
            ),
        )

    # -------------------------------------------------------------------------
    def _evidence_for_plan(
        self,
        plan: MapPlan,
        state: AgentState,
        context: ToolExecutionContext,
    ) -> list[AgentEvidenceEnvelope]:
        refs = [
            action.evidence_ref
            for action in plan.actions
            if isinstance(action, AddEvidenceLayerAction)
        ]
        for action in plan.actions:
            evidence_refs = getattr(action, "evidence_refs", [])
            refs.extend(str(item) for item in evidence_refs)
        ordered_refs = list(dict.fromkeys(refs))
        evidence: list[AgentEvidenceEnvelope] = []
        for ref in ordered_refs:
            if ref not in state.evidence_refs:
                raise MapPlanBuildError(
                    "unknown_evidence",
                    f"Evidence '{ref}' is not part of the current agent state.",
                )
            summary = None
            if self.evidence_repository is not None:
                summary = self.evidence_repository.get_summary(
                    ref,
                    conversation_id=context.conversation_id,
                )
            if summary is None:
                evidence.append(
                    AgentEvidenceEnvelope(
                        ok=True,
                        status="available",
                        evidence_ref=ref,
                    )
                )
                continue
            evidence.append(
                AgentEvidenceEnvelope(
                    ok=summary.status != "failed",
                    status=summary.status,
                    evidence_ref=summary.evidence_id,
                    summary=dict(summary.summary),
                    provenance=dict(summary.provenance),
                    map_eligibility=summary.map_eligibility,
                )
            )
        return evidence

    # -------------------------------------------------------------------------
    @staticmethod
    def _location(state: AgentState) -> Any | None:
        return next(iter(state.location_refs.values()), None)

    # -------------------------------------------------------------------------
    @staticmethod
    def _failure(
        *,
        context: ToolExecutionContext,
        started: float,
        error_type: Any,
        code: str,
        message: str,
        recovery: Any,
    ) -> ToolResult:
        error = ToolExecutionError(
            error_type=error_type,
            code=code,
            message=message,
            retryable=False,
            recovery=recovery,
        )
        return ToolResult(
            call_id=context.call_id,
            tool_name=MapPlanService.TOOL_NAME,
            status="failed",
            summary=message,
            error=error,
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            ),
        )


__all__ = ["MapPlanService"]
