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
        memory_snapshot: dict[str, Any] | None = None,
    ) -> str:
        text = user_text.lower()
        if cls.asks_about_active_map_location(text):
            memory = memory_snapshot or {}
            active_location = memory.get("active_location")
            if not isinstance(active_location, dict):
                active_visualization = memory.get("active_visualization")
                active_location = (
                    active_visualization.get("resolved_location")
                    if isinstance(active_visualization, dict)
                    else None
                )
            if isinstance(active_location, dict):
                label = str(active_location.get("label") or "").strip()
                if label:
                    return f"The map is currently centered on {label}."
            return "There is no active map location in this conversation."
        if cls.asks_about_active_map_overlays(text):
            active_visualization = cls._active_visualization(memory_snapshot)
            if active_visualization is None:
                return "There is no active map visualization in this conversation."
            overlay_ids = [
                item
                for item in active_visualization.get("overlay_ids", [])
                if isinstance(item, str) and item.strip()
            ]
            if not overlay_ids:
                return "The current map has no overlays requested."
            descriptions = active_visualization.get("overlays")
            labels: list[str] = []
            if isinstance(descriptions, list):
                for overlay_id in overlay_ids:
                    description = next(
                        (
                            item
                            for item in descriptions
                            if isinstance(item, dict) and item.get("id") == overlay_id
                        ),
                        None,
                    )
                    label = description.get("label") if isinstance(description, dict) else None
                    labels.append(str(label or cls.humanize_identifier(overlay_id)))
            else:
                labels = [cls.humanize_identifier(item) for item in overlay_ids]
            return "The current map includes these overlays: " + ", ".join(labels) + "."
        if cls.asks_about_active_map_summary(text):
            active_visualization = cls._active_visualization(memory_snapshot)
            if active_visualization is None:
                return "There is no active map visualization in this conversation."
            location = active_visualization.get("resolved_location")
            location_label = (
                str(location.get("label") or "the active area")
                if isinstance(location, dict)
                else "the active area"
            )
            basemap = active_visualization.get("basemap")
            basemap_label = (
                str(basemap.get("label") or "the current basemap")
                if isinstance(basemap, dict)
                else cls.humanize_identifier(str(active_visualization.get("basemap_id") or "current basemap"))
            )
            overlay_message = cls.compose_general_question_message(
                "What overlays are currently requested?",
                memory_snapshot=memory_snapshot,
            )
            return f"The map is centered on {location_label} using {basemap_label}. {overlay_message}"
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
        return (
            "parser_unavailable" in ambiguities
            or "parser_timeout" in ambiguities
            or "parser_authentication_failed" in ambiguities
            or any(item.startswith("provider_") for item in ambiguities)
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def asks_about_active_map_location(text: str) -> bool:
        normalized = " ".join(str(text or "").casefold().split())
        return (
            "what city is the map centered" in normalized
            or "which city is the map centered" in normalized
            or "where is the map centered" in normalized
            or "what location is the map centered" in normalized
            or "which location is the map centered" in normalized
            or "where is the map currently centered" in normalized
            or "which city are we showing" in normalized
            or "what city are we showing" in normalized
            or "what location are we showing" in normalized
            or "what place are we showing" in normalized
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def asks_about_active_map_overlays(text: str) -> bool:
        normalized = " ".join(str(text or "").casefold().split())
        return any(
            phrase in normalized
            for phrase in (
                "what overlays are currently",
                "which overlays are currently",
                "what layers are currently",
                "which layers are currently",
                "what overlays do we have",
                "which overlays do we have",
            )
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def asks_about_active_map_summary(text: str) -> bool:
        normalized = " ".join(str(text or "").casefold().split())
        return any(
            phrase in normalized
            for phrase in (
                "summarize the current map",
                "summarise the current map",
                "describe the current map",
                "what is on the current map",
            )
        ) or (
            "summar" in normalized
            and any(
                marker in normalized
                for marker in (
                    "current map",
                    "current view",
                    "interesting area",
                    "interesting areas",
                    "current overlays",
                )
            )
        )

    # -------------------------------------------------------------------------
    @classmethod
    def is_deterministic_context_question(cls, text: str) -> bool:
        return (
            cls.asks_about_active_map_location(text)
            or cls.asks_about_active_map_overlays(text)
            or cls.asks_about_active_map_summary(text)
            or cls.asks_about_previous_user_turn(text)
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _active_visualization(memory_snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        memory = memory_snapshot or {}
        visualization = memory.get("active_visualization")
        if isinstance(visualization, dict):
            return visualization
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def humanize_identifier(value: str) -> str:
        return " ".join(str(value or "").replace("_", " ").replace("-", " ").split()).title()

    # -------------------------------------------------------------------------
    @staticmethod
    def has_parser_authentication_failure(turn_contract: Any) -> bool:
        ambiguities = set(turn_contract.ambiguities or [])
        return (
            "parser_authentication_failed" in ambiguities
            or "provider_authentication_failed" in ambiguities
        )
