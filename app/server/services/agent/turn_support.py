from __future__ import annotations

from typing import Any

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision


###############################################################################
class AgentTurnSupport:
    # -------------------------------------------------------------------------
    @staticmethod
    def build_direct_reject_decision(action_id: str) -> PolicyDecision:
        return PolicyDecision(
            plan=ExecutionPlan(state="direct_response", action_id=action_id),
            trace=DecisionTrace(steps=["general_question.direct_response"]),
        )

    # -------------------------------------------------------------------------
    @classmethod
    def compose_context_query_message(
        cls,
        query_kind: str,
        recent_messages: list[dict[str, Any]] | None = None,
        memory_snapshot: dict[str, Any] | None = None,
    ) -> str:
        if query_kind == "active_location":
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
        if query_kind == "active_overlays":
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
                    label = (
                        description.get("label")
                        if isinstance(description, dict)
                        else None
                    )
                    labels.append(str(label or cls.humanize_identifier(overlay_id)))
            else:
                labels = [cls.humanize_identifier(item) for item in overlay_ids]
            return "The current map includes these overlays: " + ", ".join(labels) + "."
        if query_kind == "active_map_summary":
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
                else cls.humanize_identifier(
                    str(active_visualization.get("basemap_id") or "current basemap")
                )
            )
            overlay_message = cls.compose_context_query_message(
                "active_overlays",
                memory_snapshot=memory_snapshot,
            )
            return f"The map is centered on {location_label} using {basemap_label}. {overlay_message}"
        if query_kind == "previous_user_request":
            previous = cls.previous_user_message(
                recent_messages or [],
            )
            if previous:
                return f"You just asked: {previous}"
            return "I do not have a previous user request in this chat yet."
        if query_kind == "capabilities":
            return (
                "I can parse geospatial requests, resolve locations, build map sessions with supported basemaps and overlays, "
                "answer coordinate and weather queries through registered tools, remember the active location for follow-ups, "
                "and reject requests that try to bypass policy or reveal secrets."
            )
        if query_kind == "failure":
            return "I could not complete the previous operation, and its diagnostic should be shown with this conversation."
        return "I can help with location-based maps, coordinates, weather, rainfall, traffic layers, and related geospatial questions."

    # -------------------------------------------------------------------------
    @classmethod
    def compose_general_question_message(
        cls,
        user_text: str,
        recent_messages: list[dict[str, Any]] | None = None,
        memory_snapshot: dict[str, Any] | None = None,
    ) -> str:
        _ = user_text
        return cls.compose_context_query_message(
            "none",
            recent_messages=recent_messages,
            memory_snapshot=memory_snapshot,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def previous_user_message(
        recent_messages: list[dict[str, Any]],
    ) -> str | None:
        for message in reversed(recent_messages):
            if str(message.get("role") or "") != "user":
                continue
            content = str(message.get("content") or "").strip()
            if content:
                return content
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def has_parser_runtime_failure(turn_contract: Any) -> bool:
        ambiguities = set(turn_contract.ambiguities or [])
        return (
            getattr(turn_contract, "failure_category", None) is not None
            or "parser_unavailable" in ambiguities
            or "parser_timeout" in ambiguities
            or "parser_authentication_failed" in ambiguities
            or any(
                item in ambiguities
                for item in (
                    "response_parsing_failed",
                    "invalid_schema_definition",
                    "context_limit_exceeded",
                )
            )
            or any(item.startswith("provider_") for item in ambiguities)
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _active_visualization(
        memory_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        memory = memory_snapshot or {}
        visualization = memory.get("active_visualization")
        if isinstance(visualization, dict):
            return visualization
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def humanize_identifier(value: str) -> str:
        return " ".join(
            str(value or "").replace("_", " ").replace("-", " ").split()
        ).title()

    # -------------------------------------------------------------------------
    @staticmethod
    def has_parser_authentication_failure(turn_contract: Any) -> bool:
        ambiguities = set(turn_contract.ambiguities or [])
        return (
            "parser_authentication_failed" in ambiguities
            or "provider_authentication_failed" in ambiguities
        )
