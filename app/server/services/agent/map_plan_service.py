"""Canonical typed map-plan application boundary."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol, cast

from server.common.typing import json_object
from server.contracts.geospatial import MapSession, OverlayInstance
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.evidence import AgentEvidenceEnvelope
from server.domain.agent.map_plan import (
    AddEvidenceLayerAction,
    MapPlan,
    SetBasemapAction,
    SetViewportAction,
)
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

    # -------------------------------------------------------------------------
    def get_summary(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> Any: ...

    # -------------------------------------------------------------------------
    def get_payload(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> tuple[Any, bytes] | None: ...

###############################################################################
class MapPlanService:
    TOOL_NAME = "apply_map_plan"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        evidence_repository: EvidenceReader | AgentEvidenceRepository | None = None,
        session_builder: MapSessionBuilder | None = None,
    ) -> None:
        self.capability_registry = capability_registry
        self.evidence_repository = evidence_repository
        self.session_builder = session_builder or MapSessionBuilder(
            capability_registry=capability_registry
        )

    # -------------------------------------------------------------------------
    async def apply(
        self,
        plan: MapPlan,
        state: AgentRunState,
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

        location = self._location_for_plan(plan, state, active_session)
        if location is None:
            return self._failure(
                context=context,
                started=started,
                error_type="state_conflict",
                code="missing_location",
                message="A validated location is required before preparing a map.",
                recovery="request_user_input",
            )

        effective_actions = self._with_default_basemap(
            plan.actions,
            active_session=active_session,
        )
        effective_plan = plan.model_copy(update={"actions": effective_actions})
        try:
            evidence = self._evidence_for_plan(effective_plan, state, context)
            candidate = await self.session_builder.build(
                location=location,
                evidence=evidence,
                active_session=active_session,
                actions=effective_actions,
            )
            candidate = self._annotate_scope_metadata(
                candidate,
                state=state,
                actions=effective_actions,
            )
            if self._valid_empty_data_only(state):
                payload = dict(candidate.payload)
                payload["result_status"] = "valid_empty"
                candidate = candidate.model_copy(
                    update={"payload": payload},
                    deep=True,
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
                        "superseded_evidence",
                        "evidence_not_renderable",
                        "unknown_layer",
                        "viewport_bounds_unavailable",
                        "render_descriptor_unavailable",
                        "render_descriptor_invalid",
                    }
                    else "semantic_validation"
                ),
                code=exc.code,
                message=exc.message,
                recovery=(
                    "replan"
                    if exc.code
                    in {
                        "unknown_layer",
                        "viewport_bounds_unavailable",
                        "evidence_not_renderable",
                        "superseded_evidence",
                        "render_descriptor_unavailable",
                        "render_descriptor_invalid",
                    }
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
            for action in effective_actions
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
    @staticmethod
    def _valid_empty_data_only(state: AgentRunState) -> bool:
        """Mark a location-only candidate when data retrieval was valid-empty."""

        data_results = [
            result
            for result in state.tool_results
            if result.tool_name == "execute_geospatial_capability"
        ]
        return bool(data_results) and all(
            result.status == "valid_empty" for result in data_results
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _annotate_scope_metadata(
        candidate: MapSession,
        *,
        state: AgentRunState,
        actions: list[Any],
    ) -> MapSession:
        """Carry validated route scope onto newly prepared evidence layers."""

        goal = state.goal
        if goal is None:
            return candidate
        evidence_refs = {
            str(action.evidence_ref)
            for action in actions
            if isinstance(action, AddEvidenceLayerAction)
            and str(action.evidence_ref).strip()
        }
        if not evidence_refs:
            return candidate
        temporal = dict(goal.temporal_scope or {})
        spatial = list(goal.spatial_scope or [])
        temporal_mode = str(temporal.get("mode") or "").strip()
        spatial_kind = (
            str(spatial[0].get("kind") or "").strip() if spatial else ""
        )
        if temporal_mode in {"", "none"} and not spatial_kind:
            return candidate
        instances: list[OverlayInstance] = []
        changed = False
        for instance in candidate.overlay_collection.instances:
            evidence_ref = str(instance.descriptor.get("evidence_ref") or "")
            if evidence_ref not in evidence_refs:
                instances.append(instance)
                continue
            descriptor = dict(instance.descriptor)
            if temporal_mode and temporal_mode != "none":
                descriptor["temporal_mode"] = temporal_mode
                if temporal.get("granularity") not in {None, "", "none"}:
                    descriptor["temporal_granularity"] = temporal["granularity"]
                for key in ("reference_time_iso", "start_time_iso", "end_time_iso"):
                    if temporal.get(key) is not None:
                        descriptor[key] = temporal[key]
            if spatial_kind:
                descriptor["analysis_scope"] = spatial_kind
            updated = instance.model_copy(update={"descriptor": descriptor}, deep=True)
            instances.append(updated)
            changed = changed or updated != instance
        if not changed:
            return candidate
        collection = candidate.overlay_collection.model_copy(
            update={"instances": instances}, deep=True
        )
        return candidate.model_copy(update={"overlay_collection": collection}, deep=True)

    # -------------------------------------------------------------------------
    def _with_default_basemap(
        self,
        actions: list[Any],
        *,
        active_session: Any | None,
    ) -> list[Any]:
        if active_session is not None or any(
            isinstance(action, SetBasemapAction) for action in actions
        ):
            return list(actions)
        return [
            SetBasemapAction(
                action="set_basemap",
                capability_id=self._default_basemap_id(),
            ),
            *actions,
        ]

    # -------------------------------------------------------------------------
    def _default_basemap_id(self) -> str:
        try:
            basemaps = self.capability_registry.list_basemaps()
        except AttributeError:
            basemaps = []
        basemap_ids = {
            str(item.get("id") or "").strip()
            for item in basemaps
            if str(item.get("id") or "").strip()
        }
        if "osm_default" in basemap_ids:
            return "osm_default"
        candidates = [
            (
                not bool(json_object(item.get("agenticUse")).get("defaultEnabled")),
                str(item.get("id") or "").strip(),
            )
            for item in basemaps
            if str(item.get("id") or "").strip()
        ]
        if candidates:
            return min(candidates)[1]
        return "osm_default"

    # -------------------------------------------------------------------------
    def _evidence_for_plan(
        self,
        plan: MapPlan,
        state: AgentRunState,
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
                    f"Evidence '{ref}' is not part of the current agent state. "
                    "Use an exact evidence_ref returned by a successful evidence-producing "
                    "tool; location refs and capability IDs are not evidence. "
                    "For a location-only map, omit add_evidence_layer and use "
                    "set_viewport with fit_location.",
                )
            repository = self.evidence_repository
            summary = (
                repository.get_summary(
                    ref,
                    conversation_id=context.conversation_id,
                )
                if repository is not None
                else None
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
            if summary.status == "superseded":
                raise MapPlanBuildError(
                    "superseded_evidence",
                    f"Evidence '{ref}' is superseded and cannot be rendered. "
                    "Use a current successful evidence_ref.",
                )
            if summary.status == "failed":
                raise MapPlanBuildError(
                    "failed_evidence",
                    f"Evidence '{ref}' failed and cannot be rendered.",
                )
            if summary.status == "valid_empty":
                raise MapPlanBuildError(
                    "evidence_not_renderable",
                    f"Evidence '{ref}' is empty and cannot satisfy a requested map layer.",
                )
            if summary.map_eligibility != "renderable":
                raise MapPlanBuildError(
                    "evidence_not_renderable",
                    f"Evidence '{ref}' is not renderable; choose a successful "
                    "evidence result with map_eligibility='renderable'.",
                )
            if summary.kind not in {
                "vector",
                "raster_descriptor",
                "provider_layer_descriptor",
                "capability_result",
            }:
                raise MapPlanBuildError(
                    "evidence_not_renderable",
                    f"Evidence '{ref}' is not a supported vector or raster layer.",
                )
            payload: Any = None
            raw_payload = (
                repository.get_payload(
                    ref,
                    conversation_id=context.conversation_id,
                )
                if repository is not None
                else None
            )
            if raw_payload is not None:
                try:
                    payload = _bounded_render_payload(json.loads(raw_payload[1]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    payload = None
            if payload is None:
                raise MapPlanBuildError(
                    "evidence_not_renderable",
                    f"Evidence '{ref}' has no usable render payload.",
                )
            evidence.append(
                AgentEvidenceEnvelope(
                    ok=summary.status not in {"failed", "superseded"},
                    status=summary.status,
                    evidence_ref=summary.evidence_id,
                    summary=dict(summary.summary),
                    provenance=dict(summary.provenance),
                    map_eligibility=summary.map_eligibility,
                    payload=payload,
                )
            )
        return evidence

    # -------------------------------------------------------------------------
    @staticmethod
    def _location_for_plan(
        plan: MapPlan,
        state: AgentRunState,
        active_session: MapSession | None,
    ) -> Any | None:
        explicit_refs = [
            str(action.location_ref).strip()
            for action in plan.actions
            if isinstance(action, SetViewportAction)
            and action.location_ref
            and action.location_ref.strip()
        ]
        if explicit_refs:
            target = " ".join(explicit_refs[0].casefold().split())
            for key, location in state.location_refs.items():
                if " ".join(str(key).casefold().split()) == target:
                    return location
            return None

        route = state.route
        if (
            route is not None
            and route.primary_domain.value == "map_state"
            and str(route.operation or "").strip().casefold()
            in {
                "remove_layer",
                "set_layer_visibility",
                "set_layer_opacity",
                "set_basemap",
                "keep_only_layers",
                "fit_layer",
                "reset_view",
            }
            and active_session is not None
        ):
            return active_session.resolved_location
        route_target_refs = (
            list(route.spatial_scope.target_refs)
            if route is not None
            and route.spatial_scope is not None
            and route.spatial_scope.target_refs
            else list(route.target_refs) if route is not None else []
        )
        if route_target_refs:
            for target_ref in route_target_refs:
                target = " ".join(str(target_ref).casefold().split())
                for key, location in state.location_refs.items():
                    if " ".join(str(key).casefold().split()) == target:
                        return location
            return None
        if active_session is not None:
            return active_session.resolved_location
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


###############################################################################
def _bounded_render_payload(value: Any) -> Any:
    """Keep only the normalized feature payload required by the map client."""

    payload = json_object(value)
    features = payload.get("features")
    if isinstance(features, list):
        features = cast(list[Any], features)
        return {
            key: child
            for key, child in payload.items()
            if key != "features"
        } | {"features": features[:5000]}
    descriptor_keys = {
        "renderingMode",
        "rendering_mode",
        "url",
        "tileUrl",
        "tile_url_template",
        "serviceUrl",
        "service_url",
        "source_url",
        "layers",
        "layerId",
        "layer_id",
        "source_layer",
        "tileMatrixSet",
        "tile_matrix_set",
        "format",
        "version",
        "style",
        "bounds",
        "legend",
    }
    descriptor = {
        key: payload[key]
        for key in descriptor_keys
        if key in payload
    }
    return descriptor or None
