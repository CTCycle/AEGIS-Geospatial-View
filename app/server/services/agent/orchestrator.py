from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision
from server.domain.chat import ChatTurnRequest, ChatTurnResponse
from server.repositories.chat_history import ChatHistoryRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.native_tool_loop import (
    AgentExecutionContext,
    AgentToolLoopRequest,
    NativeToolLoop,
)
from server.services.agent.parser_service import ParserService
from server.services.agent.policy_engine import PolicyEngine
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
            agent_tool_catalog_service or AgentToolCatalogService()
        )
        self.agent_tool_catalog_service.register_with(self.tool_registry)
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
        context_usage = self.parser_service.last_context_usage
        if self._has_parser_authentication_failure(turn_contract):
            assistant_message = (
                "I could not use the configured parser model because the saved API key was rejected. "
                "Open Model Settings and replace the key before using that cloud model."
            )
            decision = self._build_direct_reject_decision(turn_contract.normalized_action.action_id)
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
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
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
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
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": None,
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
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
            )

        preflight_decision = self._evaluate_policy_preflight(turn_contract)
        if preflight_decision is not None:
            assistant_message = (
                preflight_decision.clarification.question
                if preflight_decision.clarification is not None
                else "I cannot execute this request with the current policy constraints."
            )
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": preflight_decision.model_dump(mode="json"),
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
        decision = PolicyDecision(
            plan=ExecutionPlan(
                state="direct_response",
                mode="direct_text",
                action_id=turn_contract.normalized_action.action_id,
            ),
            trace=DecisionTrace(
                steps=[
                    "1.parse_structured_request",
                    "2.build_policy_constraints",
                    "3.native_tool_loop",
                    f"4.stop:{tool_loop_result.stopped_reason}",
                ]
            ),
        )
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
        map_session = None
        memory_snapshot = latest_memory

        self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload={
                "turn_contract": turn_contract.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
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
            tool_payload=tool_payload,
            map_session=map_session,
            memory_snapshot=memory_snapshot,
            context_usage=context_usage,
        )

    def _evaluate_policy_preflight(self, turn_contract) -> PolicyDecision | None:
        trace = DecisionTrace(steps=["1.validate_task_class"])
        task_validation = self.policy_engine._validate_task_class(turn_contract)
        if task_validation is not None:
            return PolicyDecision(
                plan=ExecutionPlan(
                    state="reject",
                    action_id=turn_contract.normalized_action.action_id,
                ),
                clarification=task_validation,
                trace=trace,
            )
        trace.steps.append("2.enforce_location_requirement")
        location_policy = self.policy_engine._enforce_location_policy(turn_contract)
        if location_policy is not None:
            return PolicyDecision(
                plan=ExecutionPlan(
                    state="clarify",
                    action_id=turn_contract.normalized_action.action_id,
                ),
                clarification=location_policy,
                trace=trace,
            )
        trace.steps.append("3.enforce_safety_policy")
        safety_policy = self.policy_engine._enforce_safety_policy(turn_contract)
        if safety_policy is not None:
            return PolicyDecision(
                plan=ExecutionPlan(
                    state="reject",
                    action_id=turn_contract.normalized_action.action_id,
                ),
                clarification=safety_policy,
                trace=trace,
            )
        return None

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

    def _compose_assistant_message(
        self,
        decision,
        tool_payload: dict[str, Any] | None,
        map_payload: dict[str, Any] | None,
    ) -> str:
        if decision.plan.state == "direct_tool":
            return self._compose_direct_tool_message(decision.plan.tool_id, tool_payload)
        if decision.plan.state == "map_search" and isinstance(map_payload, dict):
            return self._compose_map_session_message(map_payload)
        if isinstance(tool_payload, dict) and tool_payload.get("error"):
            return str(tool_payload["error"])
        return "Done."

    @classmethod
    def _compose_direct_tool_message(
        cls,
        tool_id: object,
        tool_payload: dict[str, Any] | None,
    ) -> str:
        if isinstance(tool_payload, dict) and tool_payload.get("error"):
            return str(tool_payload["error"])
        result = tool_payload.get("result") if isinstance(tool_payload, dict) else None
        if not isinstance(result, dict):
            return f"Completed {cls._humanize_identifier(tool_id)}."

        nested_result = result.get("result")
        if tool_id == "location_to_coordinates":
            coordinates = result.get("coordinates")
            location = result.get("location") or cls._extract_label(tool_payload.get("location"))
            if isinstance(coordinates, dict):
                latitude = coordinates.get("latitude")
                longitude = coordinates.get("longitude")
                if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
                    return f"Coordinates for {location}: {latitude:.6f}, {longitude:.6f}."
        if tool_id == "get_weather_forecast" and isinstance(nested_result, dict):
            current = nested_result.get("selected_forecast") or nested_result.get("current")
            location = result.get("location") or cls._extract_label(tool_payload.get("location"))
            if isinstance(current, dict):
                temperature = current.get("temperature_2m")
                precipitation = current.get("precipitation")
                weather_time = current.get("time")
                details: list[str] = []
                if isinstance(temperature, (int, float)):
                    details.append(f"temperature {temperature:g} C")
                if isinstance(precipitation, (int, float)):
                    details.append(f"precipitation {precipitation:g} mm")
                if details:
                    suffix = f" at {weather_time}" if isinstance(weather_time, str) and weather_time else ""
                    return f"Weather for {location}{suffix}: {', '.join(details)}."
        return f"Completed {cls._humanize_identifier(tool_id)}."

    @classmethod
    def _compose_map_session_message(cls, map_payload: dict[str, Any]) -> str:
        location = cls._extract_label(map_payload.get("resolved_location")) or "the requested location"
        basemap = cls._extract_label(map_payload.get("basemap")) or cls._humanize_identifier(
            map_payload.get("basemap_id"),
        )
        overlay_labels = cls._extract_overlay_labels(map_payload)
        warnings = [
            cls._humanize_warning(warning)
            for warning in map_payload.get("compliance_warnings") or []
            if isinstance(warning, str) and warning.strip()
        ]

        parts = [f"Map ready for {location} using {basemap}."]
        if overlay_labels:
            parts.append(f"I added {cls._format_label_list(overlay_labels)}.")
        else:
            parts.append("No overlays were added.")
        if warnings:
            parts.append(f"Some requested map data needs attention: {' '.join(warnings)}")
        return " ".join(parts)

    @classmethod
    def _extract_overlay_labels(cls, map_payload: dict[str, Any]) -> list[str]:
        overlays = map_payload.get("overlays")
        if isinstance(overlays, list):
            labels = [cls._extract_label(overlay) for overlay in overlays]
            human_labels = [label for label in labels if label]
            if human_labels:
                return human_labels

        overlay_ids = map_payload.get("overlay_ids")
        if not isinstance(overlay_ids, list):
            return []
        return [cls._humanize_identifier(overlay_id) for overlay_id in overlay_ids if overlay_id]

    @staticmethod
    def _extract_label(value: object) -> str | None:
        if isinstance(value, dict):
            label = value.get("label") or value.get("name") or value.get("id")
            if isinstance(label, str) and label.strip():
                return label.strip()
        return None

    @staticmethod
    def _format_label_list(labels: list[str]) -> str:
        if len(labels) == 1:
            return f"the {labels[0]} overlay"
        if len(labels) == 2:
            return f"the {labels[0]} and {labels[1]} overlays"
        return f"the {', '.join(labels[:-1])}, and {labels[-1]} overlays"

    @classmethod
    def _humanize_warning(cls, warning: str) -> str:
        message = warning.strip()
        if ":" in message:
            capability_id, detail = message.split(":", 1)
            message = f"{cls._humanize_identifier(capability_id)}: {detail.strip()}"

        replacements = {
            "TOMTOM_API_KEY": "TomTom API key",
            "GEOAPIFY_API_KEY": "Geoapify API key",
            "WINDY_WEBCAMS_API_KEY": "Windy Webcams API key",
            "osm_default": "OpenStreetMap",
            "tomtom_basic": "TomTom Basic",
            "tomtom_traffic_flow": "TomTom Traffic Flow",
            "windy_webcams": "Windy Webcams",
        }
        for raw, readable in replacements.items():
            message = message.replace(raw, readable)
        if not message.endswith("."):
            message += "."
        return message

    @staticmethod
    def _humanize_identifier(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "the default basemap"
        known_names = {
            "osm_default": "OpenStreetMap",
            "tomtom_basic": "TomTom Basic",
            "tomtom_traffic_flow": "TomTom Traffic Flow",
        }
        if value in known_names:
            return known_names[value]
        words = value.replace("-", "_").split("_")
        acronyms = {"osm": "OpenStreetMap", "modis": "MODIS", "viirs": "VIIRS"}
        return " ".join(acronyms.get(word.lower(), word.capitalize()) for word in words if word)
