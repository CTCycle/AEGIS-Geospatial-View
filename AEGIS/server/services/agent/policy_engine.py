from __future__ import annotations

from AEGIS.server.domain.agent.decision import (
    CapabilityCandidate,
    ClarificationRequest,
    DecisionTrace,
    ExecutionPlan,
    PolicyDecision,
    ResolvedLocation,
)
from AEGIS.server.domain.extraction.models import TurnParseResult
from AEGIS.server.services.agent.capability_retriever import CapabilityRetriever
from AEGIS.server.services.agent.location_resolver import LocationResolver
from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistrySnapshot


class PolicyEngine:
    def __init__(
        self,
        *,
        location_resolver: LocationResolver,
        capability_retriever: CapabilityRetriever,
    ) -> None:
        self.location_resolver = location_resolver
        self.capability_retriever = capability_retriever

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

        trace.steps.append("3.resolve_location")
        resolved = await self._resolve_location(turn, memory_snapshot)
        if isinstance(resolved, ClarificationRequest):
            return PolicyDecision(
                plan=ExecutionPlan(state="clarify", intent_id=turn.normalized_intent.intent_id),
                clarification=resolved,
                trace=trace,
            )

        trace.steps.append("4.validate_ambiguity")
        if turn.ambiguities:
            return PolicyDecision(
                plan=ExecutionPlan(state="clarify", intent_id=turn.normalized_intent.intent_id),
                clarification=self._build_clarification(turn.ambiguities),
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
        mode_state, selected_tool = self._select_execution_mode(turn, candidates)

        trace.steps.append("9.build_execution_plan")
        plan = ExecutionPlan(
            state=mode_state,
            mode="direct_text" if mode_state == "direct_tool" else "map",
            intent_id=turn.normalized_intent.intent_id,
            basemap_id=self._select_basemap(candidates),
            overlay_ids=[item.capability_id for item in candidates if item.kind == "overlay"][:4],
            tool_id=selected_tool.capability_id if selected_tool is not None else None,
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
        if turn.normalized_intent.requires_location and not turn.location_signals and not turn.conversation_context.memory_snapshot.get("active_location"):
            return ClarificationRequest(
                question="Which location should I use?",
                reason="Location is required for this intent.",
                missing_fields=["location"],
            )
        return None

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
    ) -> tuple[str, CapabilityCandidate | None]:
        if turn.task_class == "direct_query":
            tool = next((item for item in candidates if item.kind == "tool" and item.supports_direct_text), None)
            return "direct_tool", tool
        if turn.disallowed_patterns:
            return "reject", None
        return "map_search", None

    def _build_clarification(self, ambiguities: list[str]) -> ClarificationRequest:
        return ClarificationRequest(
            question="I need one clarification before continuing. Could you provide a specific location?",
            reason=", ".join(ambiguities),
            missing_fields=["location"],
        )

    def _select_basemap(self, candidates: list[CapabilityCandidate]) -> str:
        preferred = next((item.capability_id for item in candidates if item.kind == "basemap"), None)
        return preferred or "osm_default"

    def _default_tool_for_intent(self, intent_id: str) -> str:
        return {
            "location_lookup": "location_to_coordinates",
            "weather": "get_weather_forecast",
            "air_quality": "get_air_quality_forecast",
            "poi": "get_nearby_poi",
        }.get(intent_id, "location_to_coordinates")
