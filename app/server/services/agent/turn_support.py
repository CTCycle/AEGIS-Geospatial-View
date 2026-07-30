from __future__ import annotations

from typing import Any

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision

###############################################################################
class AgentTurnSupport:

    # -------------------------------------------------------------------------
    @staticmethod
    def build_native_agent_messages(
        *,
        turn_contract: Any,
        memory_snapshot: dict[str, Any],
        constraints: Any,
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
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
                    f"Active conversation instructions:\n{active_instructions or []}\n\n"
                    f"Current task state:\n{task_snapshot or {}}\n\n"
                    f"Policy constraints:\n{constraints}"
                ),
            },
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def build_direct_reject_decision(action_id: str) -> PolicyDecision:
        return PolicyDecision(
            plan=ExecutionPlan(state="direct_response", action_id=action_id),
            trace=DecisionTrace(steps=["general_question.direct_response"]),
        )

    # -------------------------------------------------------------------------
    @classmethod
    def compose_general_question_message(
        cls,
        user_text: str,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> str:
        text = user_text.lower()
        if cls.asks_about_previous_user_turn(text):
            previous = cls.previous_user_message(
                recent_messages or [],
                current_text=user_text,
            )
            if previous:
                return f"You just asked: {previous}"
            return "I do not have a previous user request in this chat yet."
        if "capabil" in text or "model" in text:
            return (
                "I can parse geospatial requests, resolve locations, build map sessions with supported basemaps and overlays, "
                "answer coordinate and weather queries through registered tools, remember the active location for follow-ups, "
                "and reject requests that try to bypass policy or reveal secrets."
            )
        if "basemap" in text and "layer" in text:
            return (
                "A basemap is the geographic background or reference, such as streets, satellite imagery, or terrain. "
                "A map layer adds thematic or operational data above that background and can be shown or hidden independently."
            )
        return "I can help with location-based maps, coordinates, weather, rainfall, traffic layers, and related geospatial questions."

    # -------------------------------------------------------------------------
    @staticmethod
    def asks_about_previous_user_turn(text: str) -> bool:
        return (
            "what did i just ask" in text
            or "what was my last question" in text
            or "what did i ask you to remember" in text
            or "what did i ask you to keep in mind" in text
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def previous_user_message(
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

    # -------------------------------------------------------------------------
    @staticmethod
    def is_capability_question(user_text: str) -> bool:
        text = user_text.lower()
        return "capabil" in text and any(
            marker in text for marker in ("model", "you", "app", "aegis")
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def has_parser_runtime_failure(turn_contract: Any) -> bool:
        ambiguities = set(turn_contract.ambiguities or [])
        if "parser_unavailable" not in ambiguities and not any(
            item.startswith("provider_") for item in ambiguities
        ):
            return False
        if not hasattr(turn_contract, "task_class"):
            return True
        return (
            turn_contract.task_class == "unclear"
            or turn_contract.normalized_action.action_id == "unknown"
            or (
                turn_contract.normalized_action.requires_location
                and not turn_contract.location_signals
                and not turn_contract.conversation_context.memory_snapshot.get(
                    "active_location"
                )
            )
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def has_parser_authentication_failure(turn_contract: Any) -> bool:
        return "parser_authentication_failed" in set(turn_contract.ambiguities or [])
