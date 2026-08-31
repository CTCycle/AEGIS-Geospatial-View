from __future__ import annotations

from typing import Any

from server.common.typing import is_json_object, json_array, json_object
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
            memory = json_object(memory_snapshot)
            active_location = json_object(memory.get("active_location"))
            if not active_location:
                active_visualization = json_object(
                    memory.get("active_visualization")
                )
                active_location = json_object(
                    active_visualization.get("resolved_location")
                )
            label = str(active_location.get("label") or "").strip()
            if label:
                return f"The map is currently centered on {label}."
            return "There is no active map location in this conversation."
        if query_kind == "active_overlays":
            active_visualization = cls._active_visualization(memory_snapshot)
            if active_visualization is None:
                return "There is no active map visualization in this conversation."
            overlay_collection = json_object(
                active_visualization.get("overlay_collection")
            )
            instances = json_array(overlay_collection.get("instances"))
            overlay_instances = [
                item for item in instances if is_json_object(item)
            ]
            if not overlay_instances:
                return "The current map has no overlays requested."
            labels = [
                str(
                    item.get("label")
                    or cls.humanize_identifier(
                        str(item.get("capability_id") or item.get("instance_id"))
                    )
                )
                for item in overlay_instances
            ]
            return "The current map includes these overlays: " + ", ".join(labels) + "."
        if query_kind == "active_map_summary":
            active_visualization = cls._active_visualization(memory_snapshot)
            if active_visualization is None:
                return "There is no active map visualization in this conversation."
            location = json_object(active_visualization.get("resolved_location"))
            location_label = str(location.get("label") or "the active area")
            basemap = json_object(active_visualization.get("basemap"))
            basemap_label = (
                str(basemap.get("label") or "the current basemap")
                if basemap
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
        visualization = json_object(json_object(memory_snapshot).get("active_visualization"))
        return visualization or None

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
