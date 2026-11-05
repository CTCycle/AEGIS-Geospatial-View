"""Canonical typed map-plan application boundary."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol, cast

from server.common.identifiers import location_ref_matches, normalize_target_key
from server.common.logging_handlers import log_unexpected_failure
from server.common.typing import json_object
from server.contracts.geospatial import MapSession, OverlayInstance
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.evidence import AgentEvidenceEnvelope
from server.domain.agent.task_ledger import map_fingerprint
from server.domain.agent.map_plan import (
    AddEvidenceLayerAction,
    MapPlan,
    MarkLocationsAction,
    SetBasemapAction,
    SetViewportAction,
)
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.services.agent.basemap_intent import match_requested_basemap, names_centre
from server.services.agent.capability_execution import ToolExecutionContext
from server.services.agent.completion import evidence_numbers
from server.services.agent.final_answer_check import value_is_supported
from server.services.agent.tool_registry import (
    is_active_map_update,
    unresolved_route_targets,
)
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.map_session_builder import (
    MapPlanBuildError,
    MapSessionBuilder,
    session_view_bbox,
    viewport_covering_evidence,
    viewport_covering_points,
)

LOGGER = logging.getLogger(__name__)

###############################################################################
def _ungrounded_annotation(plan: MapPlan, state: AgentRunState) -> str | None:
    """Return the first marker label whose number the run's evidence lacks."""

    numbers = evidence_numbers(state)
    for action in plan.actions:
        if not isinstance(action, MarkLocationsAction):
            continue
        for label in action.annotations.values():
            for raw in re.findall(r"\d+(?:\.\d+)?", label):
                if not value_is_supported(raw, "", numbers):
                    return label
    return None


###############################################################################
def _is_location_only_map(state: AgentRunState) -> bool:
    route = state.route
    contract = state.completion_contract
    return not (
        route is None
        or contract is None
        or contract.evidence_required
        or route.analysis is not None
        or route.location_mode != "target"
        or route.presentation not in {"map", "both"}
        or is_active_map_update(route, state)
    )

###############################################################################
def _already_shown(state: AgentRunState, candidate: MapSession) -> bool:
    """Whether the candidate is the committed map and the user still sees it.

    The client-reported view, when present, must still contain the map's
    centre; after the user panned away the same map is rendered again.
    """

    active = state.active_map_session
    if active is None or map_fingerprint(active) != map_fingerprint(candidate):
        return False
    bounds = json_object(state.map_memory.get("current_view")).get("bounds")
    if not isinstance(bounds, list):
        return True
    edges = [float(value) for value in cast(list[object], bounds) if isinstance(value, (int, float))]
    if len(edges) != 4:
        return True
    west, south, east, north = edges
    viewport = candidate.viewport
    return west <= viewport.center_longitude <= east and south <= viewport.center_latitude <= north

###############################################################################
def targets_outside_view(state: AgentRunState, view: list[float]) -> list[str]:
    """Requested places a location-only map view does not frame.

    Evidence maps widen their view to the data and are checked per layer; a
    location-only map has nothing else to prove a place is shown, so each
    resolved route target must lie inside the view that will be rendered.
    """

    west, south, east, north = view
    return [
        target
        for target, matches in _resolved_target_locations(state)
        if not any(
            west <= location.longitude <= east and south <= location.latitude <= north
            for location in matches
        )
    ]

###############################################################################
def _resolved_target_locations(state: AgentRunState) -> list[tuple[str, list[Any]]]:
    if not _is_location_only_map(state) or state.route is None:
        return []
    resolved: list[tuple[str, list[Any]]] = []
    for target in state.route.target_refs:
        matches = [
            location
            for key, location in state.location_refs.items()
            if location_ref_matches(str(target), str(key), location.label)
        ]
        if matches:
            resolved.append((str(target), matches))
    return resolved

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

        unresolved = unresolved_route_targets(state) if _is_location_only_map(state) else []
        if unresolved:
            # A location from an earlier turn must not stand in for a requested
            # place whose own resolution is missing, failed or ambiguous.
            return self._failure(
                context=context,
                started=started,
                error_type="state_conflict",
                code="target_not_resolved",
                message=(
                    f"'{unresolved[0]}' is not resolved. Resolve it with "
                    "resolve_geospatial_location first; if it is ambiguous, ask the "
                    "user which place they mean instead of mapping another place."
                ),
                recovery="choose_alternate_tool",
            )

        marked_locations: dict[str, Any] = {}
        for action in plan.actions:
            if not isinstance(action, MarkLocationsAction):
                continue
            for ref in action.location_refs:
                resolved = self._resolved_ref(ref, state)
                if resolved is None:
                    return self._failure(
                        context=context,
                        started=started,
                        error_type="state_conflict",
                        code="missing_location",
                        message=(
                            f"Resolve '{ref}' with resolve_geospatial_location "
                            "before marking it, then pass the returned location ref."
                        ),
                        recovery="choose_alternate_tool",
                    )
                marked_locations[ref] = resolved

        ungrounded = _ungrounded_annotation(plan, state)
        if ungrounded is not None:
            return self._failure(
                context=context,
                started=started,
                error_type="semantic_validation",
                code="annotation_not_in_evidence",
                message=(
                    f"The marker label '{ungrounded}' has a number the retrieved data "
                    "does not contain. Label markers only with values from the evidence."
                ),
                recovery="correct_arguments",
            )

        location = self._location_for_plan(plan, state, active_session)
        if location is None:
            named = self._explicit_location_refs(plan)
            if named:
                # The model named a place it has not resolved yet; that is a
                # tool-order correction, not a question for the user.
                return self._failure(
                    context=context,
                    started=started,
                    error_type="state_conflict",
                    code="missing_location",
                    message=(
                        f"Resolve '{named[0]}' with resolve_geospatial_location "
                        "before fitting the map to it."
                    ),
                    recovery="choose_alternate_tool",
                )
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
            user_message=state.user_message,
            previous_user_message=next(
                (
                    str(message.get("content") or "")
                    for message in reversed(state.recent_messages)
                    if message.get("role") == "user"
                ),
                "",
            ),
        )
        if names_centre(state.user_message):
            # "Zoom in on the city centre" centres on the shown place, whatever
            # anchor the model chose.
            effective_actions = [
                action.model_copy(update={"anchor": "location"})
                if isinstance(action, SetViewportAction) and action.strategy == "zoom_in"
                else action
                for action in effective_actions
            ]
        if marked_locations and active_session is not None:
            # Markers annotate the map the user is looking at; re-fitting the
            # shown place would discard their zoom. The marker action widens
            # the view itself when a marker falls outside it.
            effective_actions = [
                action
                for action in effective_actions
                if not (
                    isinstance(action, SetViewportAction)
                    and action.strategy == "fit_location"
                )
            ]
        effective_plan = plan.model_copy(update={"actions": effective_actions})
        try:
            evidence = self._evidence_for_plan(effective_plan, state, context)
            candidate = await self.session_builder.build(
                location=location,
                evidence=evidence,
                active_session=active_session,
                actions=effective_actions,
                current_view_bounds=json_object(
                    state.map_memory.get("current_view")
                ).get("bounds"),
                marked_locations=marked_locations,
            )
            candidate = self._annotate_scope_metadata(
                candidate,
                state=state,
                actions=effective_actions,
            )
            if state.route is not None and len(state.route.target_refs) > 1 and evidence:
                candidate = viewport_covering_evidence(candidate, evidence)
            if self._valid_empty_data_only(state):
                payload = dict(candidate.payload)
                payload["result_status"] = "valid_empty"
                candidate = candidate.model_copy(
                    update={"payload": payload},
                    deep=True,
                )
            # Several requested places need one view that contains them all,
            # whatever the model's viewport actions framed.
            candidate = viewport_covering_points(
                candidate,
                [
                    (matches[-1].longitude, matches[-1].latitude)
                    for _, matches in _resolved_target_locations(state)
                ],
            )
            outside = targets_outside_view(state, session_view_bbox(candidate))
            if outside:
                return self._failure(
                    context=context,
                    started=started,
                    error_type="semantic_validation",
                    code="targets_not_in_view",
                    message=(
                        "The map view must contain every requested place. Not in view: "
                        + ", ".join(outside)
                        + ". Fit the viewport so all requested places are visible."
                    ),
                    recovery="correct_arguments",
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
        except Exception as exc:
            log_unexpected_failure(
                LOGGER, exc, stage="map_candidate_build",
                run_id=context.run_id or state.run_id, call_id=context.call_id,
            )
            return self._failure(
                context=context,
                started=started,
                error_type="invalid_tool_output",
                code="map_candidate_invalid",
                message="The map candidate could not be built from validated inputs.",
                recovery="terminal",
            )

        evidence_refs = [
            action.evidence_ref
            for action in effective_actions
            if isinstance(action, AddEvidenceLayerAction)
        ]
        if _already_shown(state, candidate):
            # The committed map is exactly this candidate and still in the
            # user's view: rendering it again would change nothing, so the
            # presentation counts as delivered by the map already shown.
            state.render_verified = True
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.TOOL_NAME,
                status="success",
                summary="The map already shows exactly this plan; nothing was re-rendered.",
                data={"render_status": "already_shown", "basemap_id": candidate.basemap_id},
                evidence_refs=list(dict.fromkeys(evidence_refs)),
                metadata=ToolExecutionMetadata(
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    evidence_refs=list(dict.fromkeys(evidence_refs)),
                ),
            )
        state.prepared_map_session = candidate
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

        if state.route is not None and state.route.analysis is not None:
            transforms = [result for result in state.tool_results if result.tool_name == "transform_evidence"]
            return bool(transforms) and transforms[-1].status == "valid_empty"
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
        user_message: str,
        previous_user_message: str = "",
    ) -> list[Any]:
        try:
            basemaps = self.capability_registry.list_basemaps()
        except AttributeError:
            basemaps = []
        requested = match_requested_basemap(user_message, basemaps)
        if requested is None and active_session is None:
            # Before the first map, a style named in the previous turn ("switch
            # to satellite", answered with "which place?") still applies.
            requested = match_requested_basemap(previous_user_message, basemaps)
        if any(isinstance(action, SetBasemapAction) for action in actions):
            # A style the user named outranks a different model-chosen basemap.
            if requested is None:
                return list(actions)
            return [
                action.model_copy(update={"capability_id": requested})
                if isinstance(action, SetBasemapAction)
                else action
                for action in actions
            ]
        if active_session is not None:
            if requested is None or requested == active_session.basemap_id:
                return list(actions)
            return [
                SetBasemapAction(action="set_basemap", capability_id=requested),
                *actions,
            ]
        return [
            SetBasemapAction(
                action="set_basemap",
                capability_id=requested or self._default_basemap_id(),
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
                "derived",
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
        if active_session is not None and any(
            isinstance(action, MarkLocationsAction) for action in plan.actions
        ):
            # Marking places keeps the shown map as the subject.
            return active_session.resolved_location
        explicit_refs = MapPlanService._explicit_location_refs(plan)
        if explicit_refs:
            location = MapPlanService._resolved_ref(explicit_refs[0], state)
            if location is None and active_session is not None:
                shown = active_session.resolved_location
                if location_ref_matches(explicit_refs[0], shown.label, shown.label):
                    return shown
            return location

        route = state.route
        if (
            route is not None
            and is_active_map_update(route, state)
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
                location = MapPlanService._resolved_ref(str(target_ref), state)
                if location is not None:
                    return location
            return None
        if active_session is not None:
            return active_session.resolved_location
        return next(iter(state.location_refs.values()), None)

    # -------------------------------------------------------------------------
    @staticmethod
    def _explicit_location_refs(plan: MapPlan) -> list[str]:
        return [
            str(action.location_ref).strip()
            for action in plan.actions
            if isinstance(action, SetViewportAction)
            and action.location_ref
            and action.location_ref.strip()
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _resolved_ref(ref: str, state: AgentRunState) -> Any | None:
        """Prefer the exactly keyed location, then a differently qualified one."""

        target = normalize_target_key(ref)
        exact = next(
            (
                location
                for key, location in state.location_refs.items()
                if normalize_target_key(str(key)) == target
            ),
            None,
        )
        return exact or next(
            (
                location
                for key, location in state.location_refs.items()
                if location_ref_matches(ref, str(key), location.label)
            ),
            None,
        )

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
    render_payload = json_object(payload.get("render"))
    if render_payload:
        bounded_render = _bounded_render_payload(render_payload)
        if bounded_render is not None:
            return {"render": bounded_render}
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
        "source_protocol",
        "layers",
        "layerId",
        "layer_id",
        "source_layer",
        "tileMatrixSet",
        "tile_matrix_set",
        "tile_size",
        "min_zoom",
        "max_zoom",
        "format",
        "version",
        "style",
        "crs",
        "time",
        "default_time",
        "attribution",
        "attribution_url",
        "bounds",
        "legend",
    }
    descriptor = {
        key: payload[key]
        for key in descriptor_keys
        if key in payload
    }
    return descriptor or None
