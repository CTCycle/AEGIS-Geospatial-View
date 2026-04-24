from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.services.agent.location_memory import LocationMemoryService
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.agent.policy_engine import PolicyEngine
from AEGIS.server.services.agent.tool_registry import ToolRegistry
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.search.request_builder import RequestBuilder

LOGGER = logging.getLogger(__name__)


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
        history_repo: ChatHistoryRepository | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.parser_service = parser_service
        self.location_memory_service = location_memory_service
        self.policy_engine = policy_engine
        self.tool_registry = tool_registry
        self.request_builder = request_builder
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

        decision = await self.policy_engine.decide(
            turn=turn_contract,
            memory_snapshot=latest_memory,
            runtime_registry=self.tool_registry.runtime_registry.build_snapshot(),
            capability_registry=self.search_orchestrator.capability_registry,
        )

        tool_payload: dict[str, Any] | None = None
        map_session = None
        assistant_message = "I need a clarification before I continue."
        memory_snapshot = latest_memory

        if decision.plan.state == "direct_tool" and decision.resolved_location is not None:
            tool_id = decision.plan.tool_id or "location_to_coordinates"
            tool_payload = await self.tool_registry.execute(tool_id, decision.plan, decision.resolved_location)
            assistant_message = self._compose_assistant_message(decision, tool_payload, None)
            memory_snapshot = self.location_memory_service.update_memory_snapshot(
                latest_memory,
                decision.resolved_location,
                turn_contract.normalized_intent,
            )
        elif decision.plan.state == "map_search" and decision.resolved_location is not None:
            request = self.request_builder.build_location_search_request(
                decision.plan,
                decision.resolved_location,
            )
            map_session = await self.search_orchestrator.execute(request)
            LOGGER.info(
                "chat_turn_map_session request_id=%s basemap_id=%s overlay_ids=%s warnings=%s",
                request_id,
                map_session.basemap_id,
                map_session.overlay_ids,
                map_session.compliance_warnings,
            )
            assistant_message = self._compose_assistant_message(decision, None, map_session.model_dump(mode="json"))
            memory_snapshot = self.location_memory_service.update_memory_snapshot(
                latest_memory,
                decision.resolved_location,
                turn_contract.normalized_intent,
            )
        elif decision.clarification is not None:
            assistant_message = decision.clarification.question
        elif decision.plan.state == "reject":
            assistant_message = "I cannot execute this request with the current policy constraints."

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
        )

    def _compose_assistant_message(
        self,
        decision,
        tool_payload: dict[str, Any] | None,
        map_payload: dict[str, Any] | None,
    ) -> str:
        if decision.plan.state == "direct_tool":
            return f"Executed direct tool '{decision.plan.tool_id}'."
        if decision.plan.state == "map_search" and isinstance(map_payload, dict):
            return self._compose_map_session_message(map_payload)
        if isinstance(tool_payload, dict) and tool_payload.get("error"):
            return str(tool_payload["error"])
        return "Done."

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
            "osm_default": "OpenStreetMap",
            "tomtom_basic": "TomTom Basic",
            "tomtom_traffic_flow": "TomTom Traffic Flow",
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
