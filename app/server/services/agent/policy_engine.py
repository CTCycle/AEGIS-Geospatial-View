from __future__ import annotations

from server.domain.agent.decision import (
    CapabilityCandidate,
    ClarificationRequest,
    DecisionTrace,
    ExecutionPlan,
    PolicyDecision,
    ResolvedLocation,
)
from server.domain.extraction.models import TurnParseResult
from server.services.agent.capability_retriever import CapabilityRetriever
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.manifest_intent_resolver import ManifestIntentResolver
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistrySnapshot

###############################################################################
class PolicyEngine:
    def __init__(
        self,
        *,
        location_resolver: LocationResolver,
        capability_retriever: CapabilityRetriever,
        manifest_intent_resolver: ManifestIntentResolver | None = None,
    ) -> None:
        self.location_resolver = location_resolver
        self.capability_retriever = capability_retriever
        self.manifest_intent_resolver = manifest_intent_resolver or ManifestIntentResolver()

    async def decide(
        self,
        turn: TurnParseResult,
        memory_snapshot: dict,
        runtime_registry: RuntimeRegistrySnapshot,
        capability_registry: CapabilityRegistry,
    ) -> PolicyDecision:
        trace = DecisionTrace(steps=[])

        trace.steps.append("1.validate_task_class")
        task_validation = self._validate_task_class(turn)
        if task_validation is not None:
            return PolicyDecision(
                plan=ExecutionPlan(state="reject", intent_id=turn.normalized_intent.intent_id),
                clarification=task_validation,
                trace=trace,
            )

        trace.steps.append("2.enforce_location_requirement")
        location_policy = self._enforce_location_policy(turn)
        if location_policy is not None:
            return PolicyDecision(
                plan=ExecutionPlan(state="clarify", intent_id=turn.normalized_intent.intent_id),
                clarification=location_policy,
                trace=trace,
            )

        trace.steps.append("2a.enforce_safety_policy")
        safety_policy = self._enforce_safety_policy(turn)
        if safety_policy is not None:
            return PolicyDecision(
                plan=ExecutionPlan(state="reject", intent_id=turn.normalized_intent.intent_id),
                clarification=safety_policy,
                trace=trace,
            )

        trace.steps.append("3.resolve_location")
        resolved = await self._resolve_location(turn, memory_snapshot)
        if isinstance(resolved, ClarificationRequest):
            return PolicyDecision(
                plan=ExecutionPlan(state="clarify", intent_id=turn.normalized_intent.intent_id),
                clarification=resolved,
                trace=trace,
            )

        trace.steps.append("4.validate_ambiguity")
        blocking_ambiguities = self._blocking_ambiguities(turn, resolved)
        if blocking_ambiguities:
            return PolicyDecision(
                plan=ExecutionPlan(state="clarify", intent_id=turn.normalized_intent.intent_id),
                clarification=self._build_clarification(blocking_ambiguities),
                resolved_location=resolved,
                trace=trace,
            )

        trace.steps.append("5.retrieve_capabilities")
        candidates = self._retrieve_candidates(turn, capability_registry)

        trace.steps.append("6.filter_runtime_availability")
        candidates = self._filter_candidates_by_runtime(candidates, runtime_registry)

        trace.steps.append("7.filter_coverage")
        candidates = self._filter_candidates_by_coverage(candidates, resolved)

        trace.steps.append("8.choose_execution_mode")
        available_ids = {
            capability_id
            for capability_id, profile in runtime_registry.profiles.items()
            if isinstance(profile, dict) and bool(profile.get("enabled_by_default", False))
        }
        manifest_resolution = self.manifest_intent_resolver.resolve(
            turn=turn,
            capability_registry=capability_registry,
            available_ids=available_ids,
        )
        overlay_ids = list(manifest_resolution.overlay_ids)
        tool_id = manifest_resolution.tool_id
        if self._explicitly_suppresses_overlays(turn):
            overlay_ids = []
            if tool_id in {"get_nearby_poi"}:
                tool_id = None
        trace.steps.append(
            "8a.resolve_manifest_concepts:"
            + ",".join(manifest_resolution.concepts or ["none"])
        )
        if manifest_resolution.ambiguous_concepts:
            return PolicyDecision(
                plan=ExecutionPlan(
                    state="clarify",
                    intent_id=turn.normalized_intent.intent_id,
                    temporal_mode=turn.temporal_signal.mode,
                    temporal_text=turn.temporal_signal.raw_text,
                    basemap_id=manifest_resolution.basemap_id,
                    overlay_ids=overlay_ids,
                ),
                clarification=ClarificationRequest(
                    question="Which data layer should I use for this map request?",
                    reason="Multiple manifest layers match: "
                    + ", ".join(manifest_resolution.ambiguous_concepts),
                    missing_fields=["layer"],
                ),
                resolved_location=resolved,
                candidates=candidates,
                trace=trace,
            )
        mode_state, selected_tool = self._select_execution_mode(
            turn,
            candidates,
            overlay_ids=overlay_ids,
            tool_id=tool_id,
        )

        trace.steps.append("9.build_execution_plan")
        plan = ExecutionPlan(
            state=mode_state,
            mode="direct_text" if mode_state == "direct_tool" else "map",
            intent_id=turn.normalized_intent.intent_id,
            temporal_mode=turn.temporal_signal.mode,
            temporal_text=turn.temporal_signal.raw_text,
            basemap_id=manifest_resolution.basemap_id,
            overlay_ids=overlay_ids,
            tool_id=tool_id
            or (selected_tool.capability_id if selected_tool is not None else None),
        )
        if mode_state == "direct_tool" and not plan.tool_id:
            plan = plan.model_copy(update={"tool_id": self._default_tool_for_intent(turn.normalized_intent.intent_id)})

        return PolicyDecision(
            plan=plan,
            resolved_location=resolved,
            candidates=candidates,
            trace=trace,
        )

    def _validate_task_class(self, turn: TurnParseResult) -> ClarificationRequest | None:
        if turn.task_class in {"map_search", "direct_query", "general_question"}:
            return None
        return ClarificationRequest(
            question="Can you clarify whether you want a map search or a direct answer?",
            reason="Task class is unclear.",
            missing_fields=["task"],
        )

    def _enforce_location_policy(self, turn: TurnParseResult) -> ClarificationRequest | None:
        if "deictic_without_memory" in turn.ambiguities:
            return ClarificationRequest(
                question="Which location should I use?",
                reason="The request refers to a previous location, but no active location is available.",
                missing_fields=["location"],
            )
        if (
            any(signal.signal_type == "deictic" for signal in turn.location_signals)
            and not turn.conversation_context.memory_snapshot.get("active_location")
        ):
            return ClarificationRequest(
                question="Which location should I use?",
                reason="The request refers to a previous location, but no active location is available.",
                missing_fields=["location"],
            )
        if turn.normalized_intent.requires_location and not turn.location_signals and not turn.conversation_context.memory_snapshot.get("active_location"):
            return ClarificationRequest(
                question="Which location should I use?",
                reason="Location is required for this intent.",
                missing_fields=["location"],
            )
        return None

    def _enforce_safety_policy(self, turn: TurnParseResult) -> ClarificationRequest | None:
        actionable_patterns = self._actionable_disallowed_patterns(turn)
        if not actionable_patterns:
            return None
        return ClarificationRequest(
            question="I cannot execute this request with the current policy constraints.",
            reason="; ".join(item.reason for item in actionable_patterns if item.reason),
            missing_fields=[],
        )

    def _actionable_disallowed_patterns(self, turn: TurnParseResult):
        return [
            item
            for item in turn.disallowed_patterns
            if item.pattern_id.strip().lower()
            not in {
                "overlay_exclusion",
                "overlay_prohibition",
                "overlay_restriction",
                "no_overlay",
                "no_overlays",
            }
        ]

    def _explicitly_suppresses_overlays(self, turn: TurnParseResult) -> bool:
        disallowed_ids = {
            str(item.pattern_id or "").strip().lower()
            for item in turn.disallowed_patterns
        }
        if disallowed_ids.intersection(
            {
                "overlay_exclusion",
                "overlay_prohibition",
                "overlay_restriction",
                "no_overlay",
                "no_overlays",
            }
        ):
            return True

        intent_markers = {
            str(item).strip().lower()
            for item in (
                *turn.normalized_intent.task_tags,
                *turn.normalized_intent.intent_tags,
                *turn.ambiguities,
            )
            if str(item).strip()
        }
        return bool(
            intent_markers.intersection(
                {
                    "overlay_exclusion",
                    "overlay_prohibition",
                    "overlay_restriction",
                    "no_overlay",
                    "no_overlays",
                    "without_overlays",
                    "basemap_only",
                }
            )
        )

    def _blocking_ambiguities(
        self,
        turn: TurnParseResult,
        resolved_location: ResolvedLocation,
    ) -> list[str]:
        non_blocking_when_resolved = {
            "potential_alternate_location",
            "alternate_location",
            "multiple_possible_locations",
        }
        blocking: list[str] = []
        for ambiguity in turn.ambiguities:
            normalized = ambiguity.strip().lower()
            if not normalized:
                continue
            if normalized in non_blocking_when_resolved and resolved_location.confidence >= 0.6:
                continue
            blocking.append(ambiguity)
        return blocking

    async def _resolve_location(self, turn: TurnParseResult, memory_snapshot: dict) -> ResolvedLocation | ClarificationRequest:
        return await self.location_resolver.resolve_location_signals(turn.location_signals, memory_snapshot)

    def _retrieve_candidates(
        self,
        turn: TurnParseResult,
        capability_registry: CapabilityRegistry,
    ) -> list[CapabilityCandidate]:
        candidates = self.capability_retriever.retrieve_candidates(turn)
        for tool in capability_registry.list_tools():
            metadata = dict(tool.get("metadata") or {})
            candidates.append(
                CapabilityCandidate(
                    capability_id=str(tool.get("id")),
                    kind="tool",
                    provider=str(tool.get("provider") or "unknown"),
                    score=0.2,
                    supports_map=bool(metadata.get("supports_map", False)),
                    supports_direct_text=bool(metadata.get("supports_direct_text", True)),
                )
            )
        return candidates

    def _filter_candidates_by_runtime(
        self,
        candidates: list[CapabilityCandidate],
        runtime_registry: RuntimeRegistrySnapshot,
    ) -> list[CapabilityCandidate]:
        result: list[CapabilityCandidate] = []
        for candidate in candidates:
            profile = runtime_registry.profiles.get(candidate.capability_id)
            if not isinstance(profile, dict):
                continue
            if not bool(profile.get("enabled_by_default", False)):
                continue
            result.append(candidate)
        return result

    def _filter_candidates_by_coverage(
        self,
        candidates: list[CapabilityCandidate],
        resolved_location: ResolvedLocation,
    ) -> list[CapabilityCandidate]:
        _ = resolved_location
        return candidates

    def _select_execution_mode(
        self,
        turn: TurnParseResult,
        candidates: list[CapabilityCandidate],
        overlay_ids: list[str] | None = None,
        tool_id: str | None = None,
    ) -> tuple[str, CapabilityCandidate | None]:
        if turn.task_class == "direct_query":
            if self._is_coordinate_lookup(turn, tool_id):
                tool = next(
                    (
                        item
                        for item in candidates
                        if item.kind == "tool"
                        and item.supports_direct_text
                        and item.capability_id == "location_to_coordinates"
                    ),
                    None,
                )
                return "direct_tool", tool
            if self._should_render_direct_query_as_map(turn, candidates, overlay_ids=overlay_ids):
                return "map_search", None
            tool = next(
                (
                    item
                    for item in candidates
                    if item.kind == "tool"
                    and item.supports_direct_text
                    and (tool_id is None or item.capability_id == tool_id)
                ),
                None,
            )
            return "direct_tool", tool
        if self._actionable_disallowed_patterns(turn):
            return "reject", None
        return "map_search", None

    def _is_coordinate_lookup(self, turn: TurnParseResult, tool_id: str | None) -> bool:
        if tool_id == "location_to_coordinates":
            return True
        intent = turn.normalized_intent
        text = " ".join(
            [
                intent.intent_id,
                intent.intent_label,
                *intent.task_tags,
                *intent.intent_tags,
            ]
        ).lower()
        markers = ("coordinate", "coordinates", "geocode", "location_lookup")
        return any(marker in text for marker in markers)

    def _should_render_direct_query_as_map(
        self,
        turn: TurnParseResult,
        candidates: list[CapabilityCandidate],
        overlay_ids: list[str] | None = None,
    ) -> bool:
        selected_overlays = (
            list(overlay_ids)
            if overlay_ids is not None
            else self._select_overlays(turn, candidates)
        )
        if selected_overlays:
            return True
        return bool(turn.normalized_intent.requested_visualizations) and any(
            item.kind in {"basemap", "overlay"} for item in candidates
        )

    def _build_clarification(self, ambiguities: list[str]) -> ClarificationRequest:
        return ClarificationRequest(
            question="I need one clarification before continuing. Could you provide a specific location?",
            reason=", ".join(ambiguities),
            missing_fields=["location"],
        )

    def _intent_text(self, turn: TurnParseResult) -> str:
        intent = turn.normalized_intent
        return " ".join(
            [
                intent.intent_id,
                intent.intent_label,
                *intent.task_tags,
                *intent.intent_tags,
                *intent.requested_visualizations,
            ]
        ).lower()

    def _select_basemap(
        self, turn: TurnParseResult, candidates: list[CapabilityCandidate]
    ) -> str:
        candidate_ids = {item.capability_id for item in candidates}
        available_ids = candidate_ids | {
            "osm_default",
            "osm_dark",
            "osm_terrain",
            "gibs_satellite",
        }
        resolution = self.manifest_intent_resolver.resolve(
            turn=turn,
            capability_registry=CapabilityRegistry(),
            available_ids=available_ids,
        )
        if resolution.basemap_id:
            return resolution.basemap_id
        intent_text = self._intent_text(turn)
        if any(marker in intent_text for marker in ("satellite", "imagery", "truecolor")):
            return "gibs_satellite"
        if "dark" in intent_text:
            return "osm_dark"
        if any(marker in intent_text for marker in ("terrain", "topographic", "topography")):
            return "osm_terrain"
        preferred = next((item.capability_id for item in candidates if item.kind == "basemap"), None)
        return preferred or "osm_default"

    def _requested_overlay_markers(self, turn: TurnParseResult) -> set[str]:
        intent_text = self._intent_text(turn)
        markers: set[str] = set()
        if any(marker in intent_text for marker in ("air quality", "air_quality", "pollution", "aerosol")):
            markers.update({"air_quality", "openaq", "aerosol"})
        if any(marker in intent_text for marker in ("traffic", "congestion", "road flow", "traffic flow")):
            markers.update({"traffic", "tomtom_traffic"})
        if any(marker in intent_text for marker in ("radar", "rainviewer")):
            markers.add("rainviewer")
        has_precipitation_intent = any(
            marker in intent_text for marker in ("precipitation", "rain", "storm")
        )
        if has_precipitation_intent:
            markers.update({"precipitation", "rainviewer", "imerg", "radar"})
        if any(marker in intent_text for marker in ("weather", "temperature", "forecast")):
            markers.update({"weather", "temperature", "forecast"})
        if any(marker in intent_text for marker in ("active fire", "active fires", "wildfire", "wildfires", "thermal anomaly", "thermal anomalies")):
            markers.update({"fire", "fires", "thermal_anomalies", "thermal_anomaly"})
        if any(marker in intent_text for marker in ("land cover", "landcover", "worldcover", "igbp")):
            markers.update({"land_cover", "landcover", "worldcover", "igbp"})
        return markers

    def _overlay_marker_score(self, overlay: CapabilityCandidate, requested_markers: set[str]) -> int:
        if not requested_markers:
            return 1 if overlay.score > 0 else 0
        normalized_id = overlay.capability_id.lower()
        score = 0
        marker_groups = (
            ({"fire", "fires", "thermal_anomalies", "thermal_anomaly"}, ("fire", "thermal_anomal")),
            ({"land_cover", "landcover", "worldcover", "igbp"}, ("land_cover", "landcover", "worldcover", "igbp")),
            ({"traffic", "tomtom_traffic"}, ("traffic",)),
            ({"air_quality", "openaq", "aerosol"}, ("air_quality", "openaq", "aerosol")),
            ({"rainviewer"}, ("rainviewer",)),
            ({"precipitation", "imerg", "radar"}, ("precipitation", "imerg", "radar", "rainviewer")),
            ({"weather", "temperature", "forecast"}, ("weather", "temperature", "forecast")),
        )
        for requested_group, id_markers in marker_groups:
            if requested_group.intersection(requested_markers) and any(marker in normalized_id for marker in id_markers):
                score += 10
        if any(marker in normalized_id for marker in requested_markers):
            score += 5
        if score > 0 and overlay.score > 0:
            score += 1
        return score

    def _select_overlays(
        self, turn: TurnParseResult, candidates: list[CapabilityCandidate]
    ) -> list[str]:
        candidate_ids = {item.capability_id for item in candidates}
        overlays = [item for item in candidates if item.kind == "overlay"]
        if candidate_ids:
            resolution = self.manifest_intent_resolver.resolve(
                turn=turn,
                capability_registry=CapabilityRegistry(),
                available_ids=candidate_ids | {"osm_default", "osm_terrain", "gibs_satellite"},
            )
            if resolution.overlay_ids:
                overlays = [
                    item
                    for item in overlays
                    if item.capability_id in set(resolution.overlay_ids)
                ]
        requested_markers = self._requested_overlay_markers(turn)
        ranked_overlays = sorted(
            overlays,
            key=lambda item: (self._overlay_marker_score(item, requested_markers), item.score),
            reverse=True,
        )
        selected: list[str] = []
        for overlay in ranked_overlays:
            marker_score = self._overlay_marker_score(overlay, requested_markers)
            normalized_id = overlay.capability_id.lower()
            if requested_markers and marker_score <= 0:
                continue
            if (
                "rainviewer" in requested_markers
                and "rainviewer" not in normalized_id
                and overlay.score <= 0
            ):
                continue
            if (
                "air_quality" in normalized_id
                and not {"air_quality", "openaq", "aerosol"}.intersection(requested_markers)
            ):
                continue
            if not requested_markers and overlay.score <= 0:
                continue
            if requested_markers and overlay.score <= 0 and selected:
                continue
            if overlay.capability_id in selected:
                continue
            selected.append(overlay.capability_id)
            if len(selected) >= 4:
                break
        return selected

    def _default_tool_for_intent(self, intent_id: str) -> str:
        return {
            "location_lookup": "location_to_coordinates",
            "weather": "get_weather_forecast",
            "air_quality": "get_air_quality_forecast",
            "poi": "get_nearby_poi",
        }.get(intent_id, "location_to_coordinates")
