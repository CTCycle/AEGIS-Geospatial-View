from __future__ import annotations

from typing import Any

from server.common.logger import logger as LOGGER
from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision, ResolvedLocation
from server.domain.agent.pipeline import (
    ConversationTaskRecord,
    TaskFailureDetail,
    VisualizationUpdate,
)
from server.domain.chat import ChatOperationResult, ChatTurnResponse
from server.domain.geographics import MapSession
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.overlay_inference import OverlayInferenceService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.chat.history_service import ChatHistoryService
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

###############################################################################
class AgentTurnStateAssembler:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        policy_engine: PolicyEngine,
        request_builder: RequestBuilder,
        overlay_inference_service: OverlayInferenceService,
        location_memory_service: LocationMemoryService,
        response_synthesizer: GroundedResponseSynthesizer,
        history_service: ChatHistoryService,
        task_state_service: ConversationTaskStateService,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.policy_engine = policy_engine
        self.request_builder = request_builder
        self.overlay_inference_service = overlay_inference_service
        self.location_memory_service = location_memory_service
        self.response_synthesizer = response_synthesizer
        self.history_service = history_service
        self.task_state_service = task_state_service

    # -------------------------------------------------------------------------
    async def build_partial_clarification_response(
        self,
        *,
        request_id: str,
        conversation_id: str,
        conversation_key: str,
        task: ConversationTaskRecord,
        turn_contract: Any,
        latest_memory: dict[str, Any],
        context_usage: Any,
    ) -> ChatTurnResponse:
        clarification = turn_contract.clarification_plan
        if not isinstance(clarification, dict):
            raise ValueError("Partial clarification requires a validated clarification plan.")
        previous_raw = self.task_state_service.snapshot(
            conversation_key
        ).active_visualization
        map_session: MapSession | None = None
        removed_layers: list[str] = []
        visualization_changes = task.visualization_changes
        requested_basemap = visualization_changes.get("basemap")
        if (
            bool(clarification.get("apply_visualization_changes"))
            and isinstance(previous_raw, dict)
        ):
            try:
                previous = MapSession.model_validate(previous_raw)
                removed_layers = [
                    layer_id
                    for layer_id in previous.overlay_ids
                    if layer_id
                    in {
                        "VIIRS_SNPP_CorrectedReflectance_TrueColor",
                        "MODIS_Terra_CorrectedReflectance_TrueColor",
                    }
                ]
                retained = [
                    layer_id
                    for layer_id in previous.overlay_ids
                    if layer_id not in removed_layers
                ]
                plan = ExecutionPlan(
                    state="map_search",
                    mode="map",
                    action_id=turn_contract.normalized_action.action_id,
                    basemap_id=(
                        str(requested_basemap)
                        if isinstance(requested_basemap, str) and requested_basemap
                        else previous.basemap_id
                    ),
                    overlay_ids=retained,
                )
                request = self.request_builder.build_location_search_request(
                    plan,
                    previous.resolved_location,
                    turn_contract=turn_contract,
                    active_visualization=previous.model_dump(mode="json"),
                )
                map_session = await self.search_orchestrator.execute(request)
            except Exception as exc:
                LOGGER.warning("Could not apply partial follow-up map update", exc_info=True)
                failure = TaskFailureDetail(
                    stage="visualization_update",
                    component="search_orchestrator",
                    sanitized_error=str(exc) or "Partial follow-up map update failed.",
                    partial_results_available=True,
                    recovery_suggestion="Retry the map refinement or keep the current map view and change only the basemap.",
                    user_explanation="I could not apply the requested map refinement to the current view.",
                )
                self.task_state_service.update_task(
                    conversation_key,
                    task.task_id,
                    status="failed",
                    failure=failure,
                    progress_summary="Partial follow-up map update failed.",
                )
        question = str(clarification.get("question") or "Can you clarify the request?")
        applied_change = (
            f"I applied the valid map change to {requested_basemap}. "
            if map_session is not None and requested_basemap
            else ""
        )
        assistant_message = f"{applied_change}{question}"
        operation = ChatOperationResult(
            kind="clarification",
            status="partial",
            message=assistant_message,
            map_session=map_session,
        )
        assistant_message = self.response_synthesizer.synthesize(
            user_text=turn_contract.user_text,
            fallback_text=assistant_message,
            operation=operation,
            map_session=map_session,
            clarification_plan=clarification,
            task_status="needs_clarification",
        )
        operation = operation.model_copy(update={"message": assistant_message})
        decision = PolicyDecision(
            plan=ExecutionPlan(
                state="clarify",
                mode="map",
                action_id=turn_contract.normalized_action.action_id,
                basemap_id=map_session.basemap_id if map_session else None,
                overlay_ids=list(map_session.overlay_ids) if map_session else [],
            ),
            trace=DecisionTrace(
                steps=[
                    "follow_up.resolve_active_visualization",
                    "clarification.apply_valid_partial_changes",
                    "clarification.request_blocking_fields",
                ]
            ),
        )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="needs_clarification",
            blocking_ambiguity=", ".join(
                map(str, clarification.get("blocking_fields") or [])
            )
            or str(clarification.get("reason") or "clarification_required"),
            progress_summary=assistant_message,
        )
        self.task_state_service.set_active_visualization(conversation_key, map_session)
        visualization_update = VisualizationUpdate(
            basemap_replacement=(
                str(requested_basemap)
                if isinstance(requested_basemap, str) and requested_basemap
                else None
            ),
            remove_layer_ids=removed_layers,
        )
        self.history_service.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_message,
            request_id=request_id,
            structured_payload={
                "turn_contract": turn_contract.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "operation": operation.model_dump(mode="json"),
                "memory_snapshot": latest_memory,
                "request_id": request_id,
            },
            map_session=map_session.model_dump(mode="json") if map_session else None,
        )
        return ChatTurnResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            assistant_message=assistant_message,
            turn_contract=turn_contract,
            decision=decision,
            operation=operation,
            map_session=map_session,
            memory_snapshot=latest_memory,
            context_usage=context_usage,
            task_snapshot=self.task_state_service.snapshot(conversation_key),
            visualization_update=visualization_update,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def failure_from_operation(
        operation: ChatOperationResult,
        tool_payload: dict[str, Any] | None,
    ) -> TaskFailureDetail | None:
        if operation.status != "failed" and operation.kind != "error":
            return None
        failed_result = next(
            (
                item
                for item in (tool_payload or {}).get("tool_results") or []
                if isinstance(item, dict) and item.get("is_error")
            ),
            None,
        )
        error_message = operation.message
        tool_name = None
        if isinstance(failed_result, dict):
            tool_name = str(failed_result.get("name") or "") or None
            error_message = str(failed_result.get("error") or error_message)
        return TaskFailureDetail(
            stage="tool_execution" if failed_result else "response_planning",
            component="agent_pipeline",
            tool_name=tool_name,
            sanitized_error=error_message,
            partial_results_available=operation.status == "partial",
            recovery_suggestion="Clarify the request or retry after the provider is available.",
            user_explanation=operation.message,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def extract_direct_result_from_tool_results(
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(tool_payload, dict):
            return None
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict):
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            direct_result = data.get("direct_result")
            if isinstance(direct_result, dict):
                return direct_result
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def extract_capability_selection_from_tool_results(
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(tool_payload, dict):
            return None
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict):
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            selection = data.get("capability_selection")
            if isinstance(selection, dict):
                return selection
        return None

    # -------------------------------------------------------------------------
    async def build_map_session_from_capability_selection(
        self,
        *,
        capability_selection: dict[str, Any],
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if not isinstance(resolved_location, ResolvedLocation):
            return None
        inferred_overlay_ids = self.infer_overlay_ids(
            turn_contract=turn_contract,
            resolved_location=resolved_location,
            existing_overlay_ids=list(capability_selection.get("overlay_ids") or []),
        )
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=capability_selection.get("basemap_id"),
            overlay_ids=inferred_overlay_ids,
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=turn_contract,
            active_visualization=(
                latest_memory.get("active_visualization")
                if isinstance(latest_memory, dict)
                else None
            ),
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    async def build_map_session_from_turn_contract(
        self,
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if not isinstance(resolved_location, ResolvedLocation):
            return None
        active_visualization = (
            latest_memory.get("active_visualization")
            if isinstance(latest_memory, dict)
            else None
        )
        existing_overlay_ids = (
            [
                item
                for item in active_visualization.get("overlay_ids") or []
                if isinstance(item, str)
            ]
            if isinstance(active_visualization, dict)
            else []
        )
        inferred_overlay_ids = self.infer_overlay_ids(
            turn_contract=turn_contract,
            resolved_location=resolved_location,
            existing_overlay_ids=existing_overlay_ids,
        )
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=self.infer_basemap_id(turn_contract),
            overlay_ids=inferred_overlay_ids,
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=turn_contract,
            active_visualization=(
                active_visualization
            ),
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    async def build_updated_memory_snapshot(
        self,
        *,
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base_snapshot = latest_memory if isinstance(latest_memory, dict) else {}
        resolved_location = await self.resolve_verified_location_for_memory(
            turn_contract=turn_contract,
            latest_memory=base_snapshot,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        if resolved_location is None:
            return base_snapshot
        return self.location_memory_service.update_memory_snapshot(
            base_snapshot,
            resolved_location,
            turn_contract.normalized_action,
        )

    # -------------------------------------------------------------------------
    async def resolve_verified_location_for_memory(
        self,
        *,
        turn_contract: Any,
        latest_memory: dict[str, Any],
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
    ) -> Any:
        if map_session is not None:
            return map_session.resolved_location
        if direct_result is None:
            return None
        if AgentResponseBuilder.tool_payload_has_error(tool_payload):
            return None
        resolved = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory,
        )
        if hasattr(resolved, "missing_fields"):
            return None
        return resolved

    # -------------------------------------------------------------------------
    async def build_combined_map_session_from_tool_results(
        self,
        *,
        tool_payload: dict[str, Any] | None,
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        if not isinstance(tool_payload, dict):
            return None
        overlay_ids: list[str] = []
        basemap_id: str | None = None

        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict) or content.get("ok") is False:
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            map_payload = data.get("map_session")
            if isinstance(map_payload, dict):
                candidate_basemap = map_payload.get("basemap_id")
                if isinstance(candidate_basemap, str) and candidate_basemap.strip() and basemap_id is None:
                    basemap_id = candidate_basemap
                for overlay_id in map_payload.get("overlay_ids") or []:
                    if isinstance(overlay_id, str) and overlay_id not in overlay_ids:
                        overlay_ids.append(overlay_id)
            selection = data.get("capability_selection")
            if isinstance(selection, dict):
                candidate_basemap = selection.get("basemap_id")
                if isinstance(candidate_basemap, str) and candidate_basemap.strip() and basemap_id is None:
                    basemap_id = candidate_basemap
                for overlay_id in selection.get("overlay_ids") or []:
                    if isinstance(overlay_id, str) and overlay_id not in overlay_ids:
                        overlay_ids.append(overlay_id)

        if not overlay_ids and basemap_id is None:
            return None

        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if hasattr(resolved_location, "missing_fields"):
            return None

        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=(
                turn_contract.requested_basemap
                or basemap_id
                or self.infer_basemap_id(turn_contract)
            ),
            overlay_ids=self.infer_overlay_ids(
                turn_contract=turn_contract,
                resolved_location=resolved_location,
                existing_overlay_ids=overlay_ids,
            ),
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=turn_contract,
            active_visualization=(
                latest_memory.get("active_visualization")
                if isinstance(latest_memory, dict)
                else None
            ),
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    def infer_overlay_ids(
        self,
        *,
        turn_contract: Any,
        resolved_location: Any,
        existing_overlay_ids: list[str],
    ) -> list[str]:
        removed_overlay_ids = self.overlay_inference_service.removed_overlay_ids(
            turn_contract=turn_contract,
            existing_overlay_ids=existing_overlay_ids,
        )
        retained_overlay_ids = [
            overlay_id
            for overlay_id in existing_overlay_ids
            if overlay_id not in removed_overlay_ids
        ]
        inferred = self.overlay_inference_service.infer_overlays(
            turn_contract=turn_contract,
            location=resolved_location,
            existing_overlay_ids=retained_overlay_ids,
        )
        merged = list(retained_overlay_ids)
        for overlay_id in inferred.overlay_ids:
            if overlay_id not in merged:
                merged.append(overlay_id)
        return merged

    # -------------------------------------------------------------------------
    @staticmethod
    def infer_basemap_id(turn_contract: Any) -> str | None:
        if turn_contract.requested_basemap:
            return turn_contract.requested_basemap
        haystack = " ".join(
            [
                turn_contract.user_text.lower(),
                turn_contract.normalized_action.action_id.lower(),
                *[item.lower() for item in turn_contract.normalized_action.task_tags],
                *[item.lower() for item in turn_contract.normalized_action.action_tags],
            ]
        )
        if any(marker in haystack for marker in ("satellite", "imagery", "true color")):
            return "esri_world_imagery"
        if any(marker in haystack for marker in ("street map", "street maps", "no satellite")):
            return "osm_default"
        if any(marker in haystack for marker in ("terrain", "elevation", "topography")):
            return "osm_terrain"
        return None
