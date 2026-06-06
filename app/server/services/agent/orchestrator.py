from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision
from server.domain.chat import ChatOperationResult, ChatTurnRequest, ChatTurnResponse
from server.domain.geographics import MapSession
from server.domain.extraction.models import LocationSignal
from server.repositories.chat_history import ChatHistoryRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.native_tool_loop import (
    AgentExecutionContext,
    AgentToolLoopRequest,
    NativeToolLoop,
)
from server.services.agent.overlay_inference import OverlayInferenceService
from server.services.agent.parser_service import ParserService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.tool_registry import ToolRegistry
from server.services.llm.factory import LLMFactory
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

LOGGER = logging.getLogger(__name__)

###############################################################################
class AgentOrchestrator:
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        parser_service: ParserService,
        location_memory_service: LocationMemoryService,
        policy_engine: PolicyEngine,
        tool_registry: ToolRegistry,
        request_builder: RequestBuilder,
        native_tool_loop: NativeToolLoop | None = None,
        agent_tool_catalog_service: AgentToolCatalogService | None = None,
        overlay_inference_service: OverlayInferenceService | None = None,
        settings_repo: ModelSettingsRepository | None = None,
        history_repo: ChatHistoryRepository | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.parser_service = parser_service
        self.location_memory_service = location_memory_service
        self.policy_engine = policy_engine
        self.tool_registry = tool_registry
        self.request_builder = request_builder
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.agent_tool_catalog_service = (
            agent_tool_catalog_service
            or AgentToolCatalogService(
                search_orchestrator=self.search_orchestrator,
                request_builder=self.request_builder,
                location_resolver=self.policy_engine.location_resolver,
                tool_registry=self.tool_registry,
                policy_engine=self.policy_engine,
            )
        )
        self.agent_tool_catalog_service.register_with(self.tool_registry)
        self.overlay_inference_service = overlay_inference_service or OverlayInferenceService()
        self.native_tool_loop = native_tool_loop or NativeToolLoop(
            provider_factory=LLMFactory(settings_repo=self.settings_repo),
            tool_registry=self.tool_registry,
        )
        self.history_repo = history_repo or ChatHistoryRepository()

    async def run_turn(self, payload: ChatTurnRequest) -> ChatTurnResponse:
        request_id = payload.request_id or f"chat-{uuid4().hex[:12]}"
        LOGGER.info(
            "chat_turn_start request_id=%s session_id=%s message_length=%s",
            request_id,
            payload.session_id,
            len(payload.message),
        )
        session = self.history_repo.upsert_session(payload.session_id, title=payload.title)
        self.history_repo.append_message(session_id=session.id, role="user", content=payload.message)

        recent_messages = self.history_repo.list_recent_messages(session.id, limit=12)
        latest_contract = self.history_repo.get_latest_turn_contract(session.id)
        latest_memory = self.history_repo.get_latest_memory_snapshot(session.id)

        turn_contract = self.parser_service.parse_turn(
            user_message=payload.message,
            memory_snapshot=latest_memory,
            conversation_messages=recent_messages,
        )
        turn_contract = self._merge_memory_location_signals(
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        context_usage = self.parser_service.last_context_usage
        if self._has_parser_authentication_failure(turn_contract):
            assistant_message = (
                "I could not use the configured parser model because the saved API key was rejected. "
                "Open Model Settings and replace the key before using that cloud model."
            )
            decision = self._build_direct_reject_decision(turn_contract.normalized_action.action_id)
            operation = ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message,
            )
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            LOGGER.info(
                "chat_turn_parser_authentication_failed request_id=%s session_id=%s",
                request_id,
                session.id,
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=decision,
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
            )
        if self._has_parser_runtime_failure(turn_contract):
            assistant_message = (
                "I could not process this request because the configured parser model is unavailable. "
                "Open Model Settings, choose an installed model, or refresh/pull the configured Ollama model."
            )
            decision = self._build_direct_reject_decision(turn_contract.normalized_action.action_id)
            operation = ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message,
            )
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            LOGGER.info(
                "chat_turn_parser_unavailable request_id=%s session_id=%s",
                request_id,
                session.id,
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=decision,
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
            )

        if turn_contract.task_class == "general_question" or self._is_capability_question(turn_contract.user_text):
            assistant_message = self._compose_general_question_message(
                turn_contract.user_text,
                recent_messages,
            )
            operation = ChatOperationResult(
                kind="capability_catalog" if self._is_capability_question(turn_contract.user_text) else "direct_answer",
                status="success",
                message=assistant_message,
            )
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": None,
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=self._build_direct_reject_decision(turn_contract.normalized_action.action_id),
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
            )

        preflight_decision = self.policy_engine.evaluate_preflight(turn_contract)
        if preflight_decision is not None:
            assistant_message = (
                preflight_decision.clarification.question
                if preflight_decision.clarification is not None
                else "I cannot execute this request with the current policy constraints."
            )
            operation = AgentResponseBuilder.build_preflight_operation_result(
                decision_state=preflight_decision.plan.state,
                assistant_message=assistant_message,
            )
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": preflight_decision.model_dump(mode="json"),
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=preflight_decision,
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
            )

        settings = self.settings_repo.get_or_create()
        constraints = self.policy_engine.build_agent_constraints(
            turn_contract,
            latest_memory,
        )
        native_context = AgentExecutionContext(
            request_id=request_id,
            session_id=str(session.id),
            parsed_request=turn_contract.model_dump(mode="json"),
            map_state=latest_memory if isinstance(latest_memory, dict) else {},
            policy_constraints={
                "requires_location": constraints.requires_location,
                "blocked_patterns": constraints.blocked_patterns,
                "allowed_tool_names": constraints.allowed_tool_names,
                **constraints.metadata,
            },
            metadata={"previous_turn_contract": latest_contract},
        )
        native_tools = self.tool_registry.list_native_tools()
        tool_loop_result = await self.native_tool_loop.run(
            AgentToolLoopRequest(
                provider=settings.agent_model_provider,
                model=settings.agent_model_name,
                messages=self._build_native_agent_messages(
                    turn_contract=turn_contract,
                    memory_snapshot=latest_memory,
                    constraints=constraints,
                ),
                tools=native_tools,
                temperature=0.2,
                max_tokens=None,
                context=native_context,
            )
        )
        decision_trace_steps = [
            "1.parse_structured_request",
            "2.build_policy_constraints",
            "3.native_tool_loop",
            f"4.stop:{tool_loop_result.stopped_reason}",
        ]
        assistant_message = tool_loop_result.final_text or "Done."
        tool_payload = {
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in tool_loop_result.tool_calls
            ],
            "tool_results": [
                {
                    "tool_call_id": result.tool_call_id,
                    "name": result.name,
                    "content": result.content,
                    "is_error": result.is_error,
                    "error": result.error,
                }
                for result in tool_loop_result.tool_results
            ],
            "iterations": tool_loop_result.iterations,
            "stopped_reason": tool_loop_result.stopped_reason,
        }
        map_session = await self._build_combined_map_session_from_tool_results(
            tool_payload=tool_payload,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        if map_session is None:
            map_session = await self._extract_map_session_from_tool_results(
                tool_payload=tool_payload,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
            )
        direct_result = self._extract_direct_result_from_tool_results(tool_payload)
        capability_selection = self._extract_capability_selection_from_tool_results(tool_payload)
        if map_session is None and capability_selection is not None:
            map_session = await self._build_map_session_from_capability_selection(
                capability_selection=capability_selection,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
            )
        if map_session is None and AgentResponseBuilder.should_build_fallback_map(
            task_class=turn_contract.task_class,
            requires_location=turn_contract.normalized_action.requires_location,
            location_signals=turn_contract.location_signals,
            tool_payload=tool_payload,
        ):
            map_session = await self._build_map_session_from_turn_contract(turn_contract, latest_memory)
        memory_snapshot = await self._build_updated_memory_snapshot(
            turn_contract=turn_contract,
            latest_memory=latest_memory,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        assistant_message = AgentResponseBuilder.build_verified_assistant_message(
            tool_loop_result.final_text,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        operation = AgentResponseBuilder.build_verified_operation_result(
            assistant_message=assistant_message,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
            user_text=turn_contract.user_text,
            is_capability_question=self._is_capability_question(turn_contract.user_text),
        )
        decision = AgentResponseBuilder.build_final_decision(
            action_id=turn_contract.normalized_action.action_id,
            operation=operation,
            trace_steps=decision_trace_steps,
        )

        self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload={
                "turn_contract": turn_contract.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "operation": operation.model_dump(mode="json"),
                "memory_snapshot": memory_snapshot,
                "previous_turn_contract": latest_contract,
                "request_id": request_id,
            },
            tool_payload=tool_payload,
            map_session=map_session.model_dump(mode="json") if map_session is not None else None,
        )

        LOGGER.info(
            "chat_turn_complete request_id=%s session_id=%s state=%s",
            request_id,
            session.id,
            decision.plan.state,
        )
        return ChatTurnResponse(
            request_id=request_id,
            session_id=session.id,
            assistant_message=assistant_message,
            turn_contract=turn_contract,
            decision=decision,
            operation=operation,
            tool_payload=tool_payload,
            map_session=map_session,
            memory_snapshot=memory_snapshot,
            context_usage=context_usage,
        )

    def _merge_memory_location_signals(
        self,
        *,
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ):
        latest_memory = latest_memory if isinstance(latest_memory, dict) else {}
        memory_signals = self.location_memory_service.resolve_explicit_references(
            turn_contract.user_text,
            latest_memory,
        )
        if not memory_signals:
            return turn_contract
        merged_signals = self._dedupe_location_signals([
            *memory_signals,
            *list(turn_contract.location_signals),
        ])
        ambiguities = [
            item
            for item in turn_contract.ambiguities
            if item not in {"missing_location", "deictic_without_memory"}
        ]
        return turn_contract.model_copy(
            update={
                "location_signals": merged_signals,
                "ambiguities": ambiguities,
            }
        )

    @staticmethod
    def _dedupe_location_signals(signals: list[LocationSignal]) -> list[LocationSignal]:
        unique: list[LocationSignal] = []
        seen: set[tuple[str, str, float | None, float | None, str]] = set()
        for signal in signals:
            key = (
                signal.signal_type,
                signal.normalized_value or signal.raw_value,
                signal.latitude,
                signal.longitude,
                signal.source,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(signal)
        return unique

    @staticmethod
    def _has_verified_map_result(tool_results: list[Any]) -> bool:
        for result in tool_results:
            if not isinstance(getattr(result, "content", None), dict):
                continue
            data = result.content.get("data")
            if isinstance(data, dict) and data.get("map_session"):
                return True
        return False

    @staticmethod
    def _build_native_agent_messages(
        *,
        turn_contract,
        memory_snapshot: dict,
        constraints,
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are the AEGIS geospatial agent. Use native tools when geospatial "
                    "catalog discovery, capability description, or execution is needed. "
                    "Do not invent tool results. Call only the provided tools by exact name. "
                    "After tool results are returned, provide a concise user-facing answer."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Parsed request:\n"
                    f"{turn_contract.model_dump_json()}\n\n"
                    f"Map memory:\n{memory_snapshot}\n\n"
                    f"Policy constraints:\n{constraints}"
                ),
            },
        ]

    @staticmethod
    def _build_direct_reject_decision(action_id: str):
        return PolicyDecision(
            plan=ExecutionPlan(state="direct_response", action_id=action_id),
            trace=DecisionTrace(steps=["general_question.direct_response"]),
        )

    @classmethod
    def _compose_general_question_message(
        cls,
        user_text: str,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> str:
        text = user_text.lower()
        if cls._asks_about_previous_user_turn(text):
            previous = cls._previous_user_message(recent_messages or [], current_text=user_text)
            if previous:
                return f"You just asked: {previous}"
            return "I do not have a previous user request in this chat yet."
        if "capabil" in text or "model" in text:
            return (
                "I can parse geospatial requests, resolve locations, build map sessions with supported basemaps and overlays, "
                "answer coordinate and weather queries through registered tools, remember the active location for follow-ups, "
                "and reject requests that try to bypass policy or reveal secrets."
            )
        return "I can help with location-based maps, coordinates, weather, rainfall, traffic layers, and related geospatial questions."

    @staticmethod
    def _asks_about_previous_user_turn(text: str) -> bool:
        return (
            "what did i just ask" in text
            or "what was my last question" in text
            or "what did i ask you to remember" in text
            or "what did i ask you to keep in mind" in text
        )

    @staticmethod
    def _previous_user_message(
        recent_messages: list[dict[str, Any]],
        *,
        current_text: str,
    ) -> str | None:
        current = str(current_text or "").strip()
        for message in reversed(recent_messages):
            if str(message.get("role") or "") != "user":
                continue
            content = str(message.get("content") or "").strip()
            if content and content != current:
                return content
        return None

    @staticmethod
    def _is_capability_question(user_text: str) -> bool:
        text = user_text.lower()
        return "capabil" in text and any(marker in text for marker in ("model", "you", "app", "aegis"))

    @staticmethod
    def _has_parser_runtime_failure(turn_contract) -> bool:
        return "parser_unavailable" in set(turn_contract.ambiguities or [])

    @staticmethod
    def _has_parser_authentication_failure(turn_contract) -> bool:
        return "parser_authentication_failed" in set(turn_contract.ambiguities or [])

    async def _extract_map_session_from_tool_results(
        self,
        *,
        tool_payload: dict[str, Any] | None,
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
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
            map_payload = data.get("map_session")
            if isinstance(map_payload, dict):
                return MapSession.model_validate(map_payload)
        return None

    def _extract_direct_result_from_tool_results(
        self,
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

    def _extract_capability_selection_from_tool_results(
        self,
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

    async def _build_map_session_from_capability_selection(
        self,
        *,
        capability_selection: dict[str, Any],
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if not hasattr(resolved_location, "model_dump"):
            return None
        inferred_overlay_ids = self._infer_overlay_ids(
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
        request = self.request_builder.build_location_search_request(plan, resolved_location)
        return await self.search_orchestrator.execute(request)

    async def _build_map_session_from_turn_contract(
        self,
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if not hasattr(resolved_location, "model_dump"):
            return None
        inferred_overlay_ids = self._infer_overlay_ids(
            turn_contract=turn_contract,
            resolved_location=resolved_location,
            existing_overlay_ids=[],
        )
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=self._infer_basemap_id(turn_contract),
            overlay_ids=inferred_overlay_ids,
        )
        request = self.request_builder.build_location_search_request(plan, resolved_location)
        return await self.search_orchestrator.execute(request)

    async def _build_updated_memory_snapshot(
        self,
        *,
        turn_contract,
        latest_memory: dict[str, Any] | None,
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base_snapshot = latest_memory if isinstance(latest_memory, dict) else {}
        resolved_location = await self._resolve_verified_location_for_memory(
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

    async def _resolve_verified_location_for_memory(
        self,
        *,
        turn_contract,
        latest_memory: dict[str, Any],
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
    ):
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

    async def _build_combined_map_session_from_tool_results(
        self,
        *,
        tool_payload: dict[str, Any] | None,
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        if not isinstance(tool_payload, dict):
            return None
        successful_entries: list[dict[str, Any]] = []
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
            entry: dict[str, Any] = {"data": data}
            map_payload = data.get("map_session")
            if isinstance(map_payload, dict):
                entry["map_session"] = map_payload
                candidate_basemap = map_payload.get("basemap_id")
                if isinstance(candidate_basemap, str) and candidate_basemap.strip() and basemap_id is None:
                    basemap_id = candidate_basemap
                for overlay_id in map_payload.get("overlay_ids") or []:
                    if isinstance(overlay_id, str) and overlay_id not in overlay_ids:
                        overlay_ids.append(overlay_id)
            selection = data.get("capability_selection")
            if isinstance(selection, dict):
                entry["capability_selection"] = selection
                candidate_basemap = selection.get("basemap_id")
                if isinstance(candidate_basemap, str) and candidate_basemap.strip() and basemap_id is None:
                    basemap_id = candidate_basemap
                for overlay_id in selection.get("overlay_ids") or []:
                    if isinstance(overlay_id, str) and overlay_id not in overlay_ids:
                        overlay_ids.append(overlay_id)
            capability_id = data.get("capability_id")
            if isinstance(capability_id, str) and capability_id and capability_id not in overlay_ids:
                if "map_session" in entry or "capability_selection" in entry:
                    overlay_ids.append(capability_id)
            if entry.keys() != {"data"}:
                successful_entries.append(entry)

        if len(overlay_ids) <= 1:
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
            basemap_id=basemap_id or self._infer_basemap_id(turn_contract),
            overlay_ids=self._infer_overlay_ids(
                turn_contract=turn_contract,
                resolved_location=resolved_location,
                existing_overlay_ids=overlay_ids,
            ),
        )
        request = self.request_builder.build_location_search_request(plan, resolved_location)
        return await self.search_orchestrator.execute(request)

    def _infer_overlay_ids(
        self,
        *,
        turn_contract,
        resolved_location,
        existing_overlay_ids: list[str],
    ) -> list[str]:
        inferred = self.overlay_inference_service.infer_overlays(
            turn_contract=turn_contract,
            location=resolved_location,
            existing_overlay_ids=existing_overlay_ids,
        )
        merged = list(existing_overlay_ids)
        for overlay_id in inferred.overlay_ids:
            if overlay_id not in merged:
                merged.append(overlay_id)
        return merged

    @staticmethod
    def _infer_basemap_id(turn_contract) -> str | None:
        haystack = " ".join(
            [
                turn_contract.user_text.lower(),
                turn_contract.normalized_action.action_id.lower(),
                *[item.lower() for item in turn_contract.normalized_action.task_tags],
                *[item.lower() for item in turn_contract.normalized_action.action_tags],
            ]
        )
        if any(marker in haystack for marker in ("satellite", "imagery", "true color")):
            return "gibs_satellite"
        if any(marker in haystack for marker in ("terrain", "elevation", "topography")):
            return "osm_terrain"
        return None
