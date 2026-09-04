from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

from typing import Any, Literal, cast

from server.common.logger import logger as LOGGER
from server.domain.agent.decision import (
    ClarificationRequest,
    DecisionTrace,
    ExecutionPlan,
    PolicyDecision,
    ResolvedLocation,
)
from server.domain.agent.pipeline import (
    ConversationTaskRecord,
    TaskFailureDetail,
    VisualizationUpdate,
)
from server.contracts.chat import ChatOperationResult, ChatTurnResponse
from server.contracts.extraction import OverlayCommand
from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    OverlayInstance,
    OverlayMutationResult,
)
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.overlay_collection import OverlayCollectionService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import (
    GroundedResponseSynthesizer,
    synthesize_response_async,
)
from server.services.chat.history_service import ChatHistoryService
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

TaskTimeoutOrigin = Literal[
    "provider_transport",
    "application_deadline",
    "cancelled",
    "frontend_or_stale_run",
    "unknown",
]


###############################################################################
class AgentTurnStateAssembler:
    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        policy_engine: PolicyEngine,
        request_builder: RequestBuilder,
        location_memory_service: LocationMemoryService,
        response_synthesizer: GroundedResponseSynthesizer,
        history_service: ChatHistoryService,
        task_state_service: ConversationTaskStateService,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.policy_engine = policy_engine
        self.request_builder = request_builder
        self.location_memory_service = location_memory_service
        self.response_synthesizer = response_synthesizer
        self.history_service = history_service
        self.task_state_service = task_state_service

    # -------------------------------------------------------------------------
    @staticmethod
    def apply_overlay_commands(
        session: MapSession,
        commands: list[OverlayCommand],
        *,
        state_session: MapSession | None = None,
    ) -> tuple[MapSession, list[OverlayMutationResult]]:
        """Apply typed overlay mutations to a native-loop map result.

        Native tool adapters and the deterministic planner share the same
        collection authority.  Binding an omitted revision here prevents a
        stale follow-up from silently replacing a newer map state.

        ``state_session`` is used when a provider fetch produced a fresh map
        session for an absent ``show``/``update`` target.  The fetched session
        supplies the candidate descriptor, while the active session remains
        authoritative for existing instances and its revision.
        """
        collection_session = state_session or session
        collection = OverlayCollectionService.from_map_session(collection_session)
        current_view = session.viewport.model_dump(mode="json")
        basemap = collection_session.basemap
        candidate_catalog = OverlayCollectionService.catalog_from_collection(
            OverlayCollectionService.from_map_session(session)
        )
        current_collection, results = OverlayCollectionService.apply_commands(
            collection,
            commands,
            catalog=candidate_catalog,
            current_view=current_view,
            basemap=basemap,
        )
        return OverlayCollectionService.merge_into_map_session(
            session, current_collection
        ), results

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
        resolved_location: ResolvedLocation | None = None,
    ) -> ChatTurnResponse:
        clarification = turn_contract.clarification_plan
        if not is_json_object(clarification):
            raise ValueError(
                "Partial clarification requires a validated clarification plan."
            )
        previous_raw = self.task_state_service.snapshot(
            conversation_key
        ).active_map_session
        map_session: MapSession | None = None
        overlay_mutation_results: list[OverlayMutationResult] = []
        visualization_changes = task.visualization_changes
        requested_basemap = visualization_changes.get("basemap")
        active_map_session = self._map_session_from_memory(previous_raw)
        if active_map_session is None:
            active_map_session = self._map_session_from_memory(
                latest_memory.get("active_visualization")
            )
        if active_map_session is not None:
            try:
                current_view = active_map_session.viewport.model_dump(mode="json")
                local_commands = OverlayCollectionService.locally_applicable_commands(
                    OverlayCollectionService.from_map_session(active_map_session),
                    turn_contract.overlay_commands,
                    current_view=current_view,
                )
                if local_commands:
                    map_session, overlay_mutation_results = self.apply_overlay_commands(
                        active_map_session,
                        local_commands,
                    )
                if bool(clarification.get("apply_visualization_changes")) and (
                    isinstance(requested_basemap, str) and requested_basemap
                ):
                    source_map = map_session or active_map_session
                    plan = ExecutionPlan(
                        state="map_search",
                        mode="map",
                        action_id=turn_contract.normalized_action.action_id,
                        basemap_id=requested_basemap,
                        overlay_ids=self._overlay_capability_ids(source_map),
                    )
                    request = self.request_builder.build_location_search_request(
                        plan,
                        source_map.resolved_location,
                        turn_contract=turn_contract,
                        active_visualization=source_map.model_dump(mode="json"),
                    )
                    fetched_map = await self.search_orchestrator.execute(request)
                    map_session = OverlayCollectionService.merge_into_map_session(
                        fetched_map,
                        source_map.overlay_collection,
                    )
            except Exception as exc:
                LOGGER.warning(
                    "Could not apply partial follow-up map update category=%s",
                    type(exc).__name__,
                )
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
        updated_memory = json_object(latest_memory)
        resolved_for_memory = resolved_location
        if isinstance(resolved_for_memory, ResolvedLocation):
            updated_memory = self.location_memory_service.update_memory_snapshot(
                updated_memory,
                resolved_for_memory,
                turn_contract.normalized_action,
            )
        removed_instance_ids = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.removed_instance_ids
        ]
        removed_instance_id_set = set(removed_instance_ids)
        removed_layer_ids = (
            [
                instance.capability_id
                for instance in active_map_session.overlay_collection.instances
                if instance.instance_id in removed_instance_id_set
            ]
            if active_map_session is not None
            else []
        )
        added_instance_ids = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.added_instance_ids
        ]
        updated_instance_ids = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.updated_instance_ids
        ]
        unmatched_selectors = [
            selector
            for result in overlay_mutation_results
            for selector in result.unmatched_selectors
        ]
        ambiguous_selectors = [
            selector
            for result in overlay_mutation_results
            for selector in result.ambiguous_selectors
        ]
        mutation_clarification = next(
            (
                result.clarification
                for result in overlay_mutation_results
                if result.clarification
            ),
            None,
        )
        applied_parts: list[str] = []
        if removed_instance_ids:
            applied_parts.append(
                f"Removed {len(removed_instance_ids)} active overlay"
                f"{'s' if len(removed_instance_ids) != 1 else ''}."
            )
        if map_session is not None and requested_basemap:
            applied_parts.append(f"Applied the requested basemap: {requested_basemap}.")
        applied_change = " ".join(applied_parts)
        if applied_change:
            applied_change += " "
        assistant_message = f"{applied_change}{question}"
        if mutation_clarification:
            assistant_message = f"{assistant_message} {mutation_clarification}"
        operation = ChatOperationResult(
            kind="clarification",
            status="partial",
            message=assistant_message,
            provider_error=turn_contract.provider_error,
            failure_category=turn_contract.failure_category,
        )
        assistant_message = await synthesize_response_async(
            self.response_synthesizer,
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
                overlay_ids=(
                    self._overlay_capability_ids(map_session) if map_session else []
                ),
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
        if map_session is not None:
            self.task_state_service.set_active_visualization(
                conversation_key, map_session
            )
        visualization_update = VisualizationUpdate(
            basemap_replacement=(
                str(requested_basemap)
                if isinstance(requested_basemap, str) and requested_basemap
                else None
            ),
            add_layer_ids=added_instance_ids,
            remove_layer_ids=removed_layer_ids,
            collection_revision=(
                map_session.overlay_collection.revision
                if map_session is not None
                else None
            ),
            added_instance_ids=added_instance_ids,
            removed_instance_ids=removed_instance_ids,
            updated_instance_ids=sorted(set(updated_instance_ids)),
            unmatched_selectors=unmatched_selectors,
            ambiguous_selectors=ambiguous_selectors,
            clarification=mutation_clarification,
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
                "memory_snapshot": updated_memory,
                "context_usage": context_usage.model_dump(mode="json")
                if context_usage is not None
                else None,
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
            memory_snapshot=updated_memory,
            context_usage=context_usage,
            task_snapshot=self.task_state_service.snapshot(conversation_key),
            visualization_update=visualization_update,
        )

    # -------------------------------------------------------------------------
    async def build_location_clarification_response(
        self,
        *,
        request_id: str,
        conversation_id: str,
        conversation_key: str,
        task: ConversationTaskRecord,
        turn_contract: Any,
        latest_memory: dict[str, Any],
        context_usage: Any,
        clarification: ClarificationRequest,
        tool_payload: dict[str, Any] | None = None,
    ) -> ChatTurnResponse:
        """Stop safely when the resolver finds a location ambiguity.

        Location resolution happens during map assembly, after preflight.  The
        clarification therefore needs its own response path; converting it to
        a generic planning error would lose the user's valid active map and
        hide the actual disambiguation question.
        """

        clarification_plan = {
            "question": clarification.question,
            "reason": clarification.reason,
            "blocking_fields": list(clarification.missing_fields or ["location"]),
            "options": [],
            "preserve_valid_results": True,
            "apply_visualization_changes": False,
        }
        operation = ChatOperationResult(
            kind="clarification",
            status="partial",
            message=clarification.question,
            provider_error=getattr(turn_contract, "provider_error", None),
            failure_category=(
                getattr(turn_contract, "failure_category", None)
                if getattr(turn_contract, "provider_error", None)
                else None
            ),
        )
        assistant_message = await synthesize_response_async(
            self.response_synthesizer,
            user_text=turn_contract.user_text,
            fallback_text=clarification.question,
            operation=operation,
            clarification_plan=clarification_plan,
            task_status="needs_clarification",
        )
        operation = operation.model_copy(update={"message": assistant_message})
        decision = PolicyDecision(
            plan=ExecutionPlan(
                state="clarify",
                mode="map",
                action_id=turn_contract.normalized_action.action_id,
            ),
            clarification=clarification,
            trace=DecisionTrace(
                steps=[
                    "location_resolution.validate_specific_target",
                    "location_resolution.request_clarification",
                ]
            ),
        )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="needs_clarification",
            blocking_ambiguity=clarification.reason,
            progress_summary=assistant_message,
        )
        memory_snapshot = json_object(latest_memory)
        self.history_service.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_message,
            request_id=request_id,
            structured_payload={
                "turn_contract": turn_contract.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "operation": operation.model_dump(mode="json"),
                "memory_snapshot": memory_snapshot,
                "context_usage": context_usage.model_dump(mode="json")
                if context_usage is not None
                else None,
                "request_id": request_id,
            },
            tool_payload=tool_payload,
            map_session=None,
        )
        return ChatTurnResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            assistant_message=assistant_message,
            turn_contract=turn_contract,
            decision=decision,
            operation=operation,
            tool_payload=tool_payload,
            map_session=None,
            memory_snapshot=memory_snapshot,
            context_usage=context_usage,
            task_snapshot=self.task_state_service.snapshot(conversation_key),
            visualization_update=VisualizationUpdate(),
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
                for item in json_array(json_object(tool_payload).get("tool_results"))
                if is_json_object(item) and item.get("is_error")
            ),
            None,
        )
        error_message = operation.message
        tool_name = None
        if is_json_object(failed_result):
            tool_name = str(failed_result.get("name") or "") or None
            error_message = str(failed_result.get("error") or error_message)
        raw_timeout_origin = (
            operation.provider_error.get("timeout_origin")
            if is_json_object(operation.provider_error)
            else None
        )
        timeout_origin = (
            cast(TaskTimeoutOrigin, raw_timeout_origin)
            if raw_timeout_origin
            in {
                "provider_transport",
                "application_deadline",
                "cancelled",
                "frontend_or_stale_run",
                "unknown",
            }
            else None
        )
        return TaskFailureDetail(
            stage="tool_execution" if failed_result else "response_planning",
            component="agent_pipeline",
            tool_name=tool_name,
            sanitized_error=error_message,
            partial_results_available=operation.status == "partial",
            recovery_suggestion="Clarify the request or retry after the provider is available.",
            user_explanation=operation.message,
            provider_error=operation.provider_error,
            timeout_origin=timeout_origin,
            failure_category=operation.failure_category,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def append_provider_events(
        tool_payload: dict[str, Any] | None,
        map_session: MapSession | None,
    ) -> None:
        """Expose provider work that is not represented by a native tool call.

        Location resolution is a required execution boundary, but it happens
        in the policy layer before a catalog capability can run.  Keep that
        provider evidence alongside native tool results so traces and
        evaluation can account for the complete request lifecycle without
        inventing a synthetic tool call.
        """
        if not is_json_object(tool_payload) or map_session is None:
            return
        provenance = map_session.resolved_location.provenance
        if provenance is None:
            return
        existing_events = [
            item
            for item in json_array(tool_payload.get("provider_events"))
            if is_json_object(item)
        ]
        resolved = map_session.resolved_location
        event: dict[str, Any] = {
            "kind": "location_resolution",
            "capability_id": "location",
            "provider": provenance.provider,
            "source_url": provenance.source_url,
            "fetched_at": provenance.fetched_at.isoformat(),
            "result_status": provenance.result_status,
            "result_type": provenance.result_type,
            "location": {
                "label": resolved.label,
                "latitude": resolved.latitude,
                "longitude": resolved.longitude,
                "bbox": resolved.bbox,
            },
        }
        event_key: tuple[object, ...] = (
            event["kind"],
            event["provider"],
            event["fetched_at"],
            resolved.latitude,
            resolved.longitude,
        )
        if not any(
            (
                item.get("kind"),
                item.get("provider"),
                item.get("fetched_at"),
                json_object(item.get("location")).get("latitude"),
                json_object(item.get("location")).get("longitude"),
            ) == event_key
            for item in existing_events
        ):
            existing_events.append(event)
        tool_payload["provider_events"] = existing_events

    # -------------------------------------------------------------------------
    @staticmethod
    def extract_direct_result_from_tool_results(
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not is_json_object(tool_payload):
            return None
        for result in json_array(tool_payload.get("tool_results")):
            if not is_json_object(result):
                continue
            content = result.get("content")
            if not is_json_object(content):
                continue
            data = content.get("data")
            if not is_json_object(data):
                continue
            direct_result = data.get("direct_result")
            if is_json_object(direct_result):
                return direct_result
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def extract_capability_selection_from_tool_results(
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not is_json_object(tool_payload):
            return None
        for result in json_array(tool_payload.get("tool_results")):
            if not is_json_object(result):
                continue
            content = result.get("content")
            if not is_json_object(content):
                continue
            data = content.get("data")
            if not is_json_object(data):
                continue
            selection = data.get("capability_selection")
            if is_json_object(selection):
                return selection
        return None

    # -------------------------------------------------------------------------
    async def build_map_session_from_capability_selection(
        self,
        *,
        capability_selection: dict[str, Any],
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
        resolved_location: ResolvedLocation | None = None,
    ) -> MapSession | ClarificationRequest | None:
        if resolved_location is None:
            resolution = await self.policy_engine.location_resolver.resolve_location_signals(
                turn_contract.location_signals,
                latest_memory or {},
            )
            if isinstance(resolution, ClarificationRequest):
                return resolution
            resolved_location = resolution
        active_visualization = (
            latest_memory.get("active_visualization")
            if is_json_object(latest_memory)
            else None
        )
        active_map_session = self._map_session_from_memory(active_visualization)
        active_visualization_object = (
            active_map_session.model_dump(mode="json") if active_map_session else {}
        )
        active_overlay_ids = self._overlay_capability_ids(active_map_session)
        inferred_overlay_ids = self.infer_overlay_ids(
            turn_contract=turn_contract,
            resolved_location=resolved_location,
            existing_overlay_ids=list(
                dict.fromkeys(
                    [
                        *active_overlay_ids,
                        *[
                            item
                            for item in json_array(
                                capability_selection.get("overlay_ids")
                            )
                            if isinstance(item, str)
                        ],
                    ]
                )
            ),
        )
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=(
                turn_contract.requested_basemap
                or active_visualization_object.get("basemap_id")
                or capability_selection.get("basemap_id")
            ),
            overlay_ids=inferred_overlay_ids,
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=turn_contract,
            active_visualization=active_visualization,
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    async def build_map_session_from_turn_contract(
        self,
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
        resolved_location: ResolvedLocation | None = None,
    ) -> MapSession | ClarificationRequest | None:
        if resolved_location is None:
            resolution = await self.policy_engine.location_resolver.resolve_location_signals(
                turn_contract.location_signals,
                latest_memory or {},
            )
            if isinstance(resolution, ClarificationRequest):
                return resolution
            resolved_location = resolution
        active_visualization = (
            latest_memory.get("active_visualization")
            if is_json_object(latest_memory)
            else None
        )
        active_map_session = self._map_session_from_memory(active_visualization)
        existing_overlay_ids = self._overlay_capability_ids(active_map_session)
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
            active_visualization=(active_visualization),
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
        resolved_location: ResolvedLocation | None = None,
    ) -> dict[str, Any]:
        base_snapshot = json_object(latest_memory)
        resolved_location = await self.resolve_verified_location_for_memory(
            turn_contract=turn_contract,
            latest_memory=base_snapshot,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
            resolved_location=resolved_location,
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
        resolved_location: ResolvedLocation | None = None,
    ) -> Any:
        if map_session is not None:
            return map_session.resolved_location
        if direct_result is None:
            return None
        if AgentResponseBuilder.tool_payload_has_error(tool_payload):
            return None
        if resolved_location is not None:
            return resolved_location
        resolved = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory,
        )
        if isinstance(resolved, ClarificationRequest):
            return None
        return resolved

    # -------------------------------------------------------------------------
    async def build_combined_map_session_from_tool_results(
        self,
        *,
        tool_payload: dict[str, Any] | None,
        turn_contract: Any,
        latest_memory: dict[str, Any] | None,
        resolved_location: ResolvedLocation | None = None,
    ) -> MapSession | ClarificationRequest | None:
        if not is_json_object(tool_payload):
            return None
        active_visualization = (
            latest_memory.get("active_visualization")
            if is_json_object(latest_memory)
            else None
        )
        active_map_session = self._map_session_from_memory(active_visualization)
        active_visualization_object = (
            active_map_session.model_dump(mode="json") if active_map_session else {}
        )
        overlay_ids = self._overlay_capability_ids(active_map_session)
        basemap_id = (
            str(active_visualization_object.get("basemap_id"))
            if isinstance(active_visualization_object.get("basemap_id"), str)
            else None
        )
        candidate_map_sessions: list[MapSession] = []

        for result in json_array(tool_payload.get("tool_results")):
            if not is_json_object(result):
                continue
            content = result.get("content")
            if not is_json_object(content) or content.get("ok") is False:
                continue
            data = content.get("data")
            if not is_json_object(data):
                continue
            result_warnings = [
                str(item).strip()
                for item in json_array(data.get("warnings"))
                if str(item).strip()
            ]
            map_payload = data.get("map_session")
            if is_json_object(map_payload):
                map_session = self._map_session_from_memory(map_payload)
                if map_session is not None:
                    if result_warnings:
                        map_session = map_session.model_copy(
                            update={
                                "compliance_warnings": list(
                                    dict.fromkeys(
                                        [
                                            *map_session.compliance_warnings,
                                            *result_warnings,
                                        ]
                                    )
                                )
                            }
                        )
                    candidate_map_sessions.append(map_session)
                    if basemap_id is None:
                        basemap_id = map_session.basemap_id
                    for overlay_id in self._overlay_capability_ids(map_session):
                        if overlay_id not in overlay_ids:
                            overlay_ids.append(overlay_id)
            selection = data.get("capability_selection")
            if is_json_object(selection):
                candidate_basemap = selection.get("basemap_id")
                if (
                    isinstance(candidate_basemap, str)
                    and candidate_basemap.strip()
                    and basemap_id is None
                ):
                    basemap_id = candidate_basemap
                for overlay_id in json_array(selection.get("overlay_ids")):
                    if isinstance(overlay_id, str) and overlay_id not in overlay_ids:
                        overlay_ids.append(overlay_id)

        # A native geospatial tool returns a validated map session together
        # with the provider-backed descriptor it fetched. Keep that result as
        # the single data authority. When a prior map exists, merge sessions
        # only when they represent the same location; a session for a new
        # location replaces the old viewport and scoped overlays so stale data
        # cannot follow the user to the new place.
        if candidate_map_sessions:
            LOGGER.info(
                "map_tool_session_merge candidates=%d active=%s candidate_overlays=%d",
                len(candidate_map_sessions),
                active_map_session is not None,
                sum(
                    len(session.overlay_collection.instances)
                    for session in candidate_map_sessions
                ),
            )
            return self._merge_tool_map_sessions(
                candidate_map_sessions,
                active_map_session=active_map_session,
                resolved_location=resolved_location,
                requested_basemap_id=self.infer_basemap_id(turn_contract),
            )

        if not overlay_ids and basemap_id is None:
            return None

        if resolved_location is None:
            resolution = await self.policy_engine.location_resolver.resolve_location_signals(
                turn_contract.location_signals,
                latest_memory or {},
            )
            if isinstance(resolution, ClarificationRequest):
                return resolution
            resolved_location = resolution
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
            active_visualization=(active_visualization),
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    @classmethod
    def _merge_tool_map_sessions(
        cls,
        candidates: list[MapSession],
        *,
        active_map_session: MapSession | None,
        resolved_location: ResolvedLocation | None,
        requested_basemap_id: str | None = None,
    ) -> MapSession:
        """Merge validated tool output without re-running the data search."""
        candidate = candidates[-1]
        canonical_location = resolved_location or candidate.resolved_location
        candidate = cls._with_canonical_location(candidate, canonical_location)

        # The basemap is map-session state, not a property of the fetched
        # overlay.  A layer-only follow-up must retain the active basemap;
        # an explicit basemap request remains authoritative for this turn.
        if (
            not requested_basemap_id
            and active_map_session is not None
            and active_map_session.basemap_id
        ):
            candidate = candidate.model_copy(
                update={
                    "basemap_id": active_map_session.basemap_id,
                    "basemap": active_map_session.basemap,
                },
                deep=True,
            )

        # Multiple successful tool calls in one bounded loop can contribute
        # different overlays. The last result owns the viewport and payload;
        # earlier results contribute only their validated overlay instances.
        candidate_instances: list[OverlayInstance] = []
        for session in candidates:
            normalized = cls._with_canonical_location(session, canonical_location)
            candidate_instances.extend(normalized.overlay_collection.instances)
        candidate_collection = cls._merge_overlay_instances(
            OverlayCollectionState(), candidate_instances
        )
        candidate = OverlayCollectionService.merge_into_map_session(
            candidate, candidate_collection
        )

        if active_map_session is None or not cls._same_resolved_location(
            active_map_session.resolved_location, canonical_location
        ):
            return candidate

        active = cls._with_canonical_location(active_map_session, canonical_location)
        merged_collection = cls._merge_overlay_instances(
            active.overlay_collection,
            [*active.overlay_collection.instances, *candidate_collection.instances],
        )
        warnings = list(
            dict.fromkeys(
                [*active.compliance_warnings, *candidate.compliance_warnings]
            )
        )
        return candidate.model_copy(
            update={
                "resolved_location": canonical_location,
                "compliance_warnings": warnings,
                "overlay_collection": merged_collection,
            },
            deep=True,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _with_canonical_location(
        session: MapSession,
        resolved_location: ResolvedLocation,
    ) -> MapSession:
        instances = [
            instance.model_copy(update={"resolved_location": resolved_location})
            for instance in session.overlay_collection.instances
        ]
        collection = session.overlay_collection.model_copy(
            update={"instances": instances},
            deep=True,
        )
        return session.model_copy(
            update={
                "resolved_location": resolved_location,
                "overlay_collection": collection,
            },
            deep=True,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _same_resolved_location(
        left: ResolvedLocation,
        right: ResolvedLocation,
    ) -> bool:
        return (
            abs(left.latitude - right.latitude) <= 1e-6
            and abs(left.longitude - right.longitude) <= 1e-6
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _merge_overlay_instances(
        cls,
        base: OverlayCollectionState,
        additions: list[OverlayInstance],
    ) -> OverlayCollectionState:
        """Union instances by stable id, then by capability and location."""
        instances = [item.model_copy(deep=True) for item in base.instances]
        changed = False
        for addition in additions:
            matching_index = next(
                (
                    index
                    for index, current in enumerate(instances)
                    if current.instance_id == addition.instance_id
                    or (
                        current.capability_id == addition.capability_id
                        and cls._same_overlay_location(current, addition)
                    )
                ),
                None,
            )
            if matching_index is None:
                instances.append(addition.model_copy(deep=True))
                changed = True
            elif instances[matching_index] != addition:
                # Provider-backed data from the current tool result is newer
                # than an active snapshot with the same scoped capability.
                instances[matching_index] = addition.model_copy(deep=True)
                changed = True
        next_revision = base.revision + 1 if changed else base.revision
        return base.model_copy(
            update={"instances": instances, "revision": next_revision},
            deep=True,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _same_overlay_location(
        left: OverlayInstance,
        right: OverlayInstance,
    ) -> bool:
        left_location = left.resolved_location
        right_location = right.resolved_location
        if left_location is None or right_location is None:
            return left.scope_key == right.scope_key
        return (
            abs(left_location.latitude - right_location.latitude) <= 1e-6
            and abs(left_location.longitude - right_location.longitude) <= 1e-6
        )

    # -------------------------------------------------------------------------
    def infer_overlay_ids(
        self,
        *,
        turn_contract: Any,
        resolved_location: Any,
        existing_overlay_ids: list[str],
    ) -> list[str]:
        _ = resolved_location
        # Overlay mutations are resolved by OverlayCollectionService after
        # the active state is loaded.  This method only builds the retrieval
        # projection for a new search and never removes an existing layer by
        # scanning user text.
        requested = [
            item
            for item in getattr(turn_contract, "requested_layers", [])
            if isinstance(item, str) and item.strip()
        ]
        for command in getattr(turn_contract, "overlay_commands", []):
            if command.action not in {"add", "show", "update"}:
                continue
            requested.extend(command.selector.capability_ids)
        merged = list(dict.fromkeys([*existing_overlay_ids, *requested]))
        return merged

    # -------------------------------------------------------------------------
    @staticmethod
    def infer_basemap_id(turn_contract: Any) -> str | None:
        requested_basemap = getattr(turn_contract, "requested_basemap", None)
        return (
            requested_basemap
            if isinstance(requested_basemap, str) and requested_basemap.strip()
            else None
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_session_from_memory(raw: object) -> MapSession | None:
        if not is_json_object(raw):
            return None
        try:
            return MapSession.model_validate(raw)
        except Exception:  # noqa: BLE001
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _overlay_capability_ids(map_session: MapSession | None) -> list[str]:
        if map_session is None:
            return []
        return [
            instance.capability_id
            for instance in map_session.overlay_collection.instances
        ]
