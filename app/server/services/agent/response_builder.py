from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

from typing import Any, Literal

from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision
from server.contracts.chat import ChatOperationResult
from server.contracts.geospatial import MapSession


###############################################################################
class AgentResponseBuilder:
    # -------------------------------------------------------------------------
    @staticmethod
    def build_final_decision(
        *,
        action_id: str,
        operation: ChatOperationResult,
        trace_steps: list[str],
    ) -> PolicyDecision:
        if operation.kind == "map_session":
            state = "map_search"
            mode = "map"
        elif operation.kind == "clarification":
            state = "clarify"
            mode = None
        elif operation.kind == "rejection":
            state = "reject"
            mode = None
        elif operation.kind == "error":
            state = "direct_response"
            mode = None
        else:
            state = (
                "direct_tool"
                if operation.direct_result is not None
                else "direct_response"
            )
            mode = "direct_text"
        return PolicyDecision(
            plan=ExecutionPlan(
                state=state,
                mode=mode,
                action_id=action_id,
            ),
            trace=DecisionTrace(steps=trace_steps),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def tool_payload_has_error(tool_payload: dict[str, Any] | None) -> bool:
        if not is_json_object(tool_payload):
            return False
        for result in json_array(tool_payload.get("tool_results")):
            if not is_json_object(result):
                continue
            content = result.get("content")
            if is_json_object(content) and content.get("ok") is False:
                return True
        return False

    # -------------------------------------------------------------------------
    @staticmethod
    def infer_failure_category(
        tool_payload: dict[str, Any] | None,
    ) -> Literal[
        "model_capability",
        "provider_api",
        "schema_definition",
        "response_parsing",
        "context_limit",
    ] | None:
        """Classify an execution failure from its typed tool error code."""

        if not is_json_object(tool_payload):
            return None
        provider_codes = {
            "auth_required",
            "provider_timeout",
            "provider_unavailable",
            "rate_limited",
            "invalid_query",
            "malformed_response",
        }
        parsing_codes = {
            "dependency_cycle",
            "dependency_failed",
            "duplicate_tool_call",
            "invalid_input_binding",
            "invalid_tool_output",
        }
        for result in json_array(tool_payload.get("tool_results")):
            if not is_json_object(result):
                continue
            content = json_object(result.get("content"))
            error = json_object(content.get("error"))
            error_message = str(
                error.get("message") or result.get("error") or ""
            ).casefold()
            code = str(
                error.get("code") or result.get("error_code") or ""
            ).strip().casefold()
            warning_texts: list[str] = []

            def collect_warnings(value: Any, *, depth: int = 0) -> None:
                if depth > 3:
                    return
                if isinstance(value, dict):
                    for key, nested in value.items():
                        normalized_key = str(key).casefold()
                        if normalized_key in {"warning", "warnings"}:
                            if isinstance(nested, str):
                                warning_texts.append(nested)
                            elif isinstance(nested, list):
                                warning_texts.extend(
                                    str(item)
                                    for item in nested
                                    if isinstance(item, (str, int, float))
                                )
                        elif normalized_key in {
                            "content",
                            "data",
                            "metadata",
                            "provenance",
                        }:
                            collect_warnings(nested, depth=depth + 1)
                elif isinstance(value, list):
                    for nested in value:
                        collect_warnings(nested, depth=depth + 1)

            collect_warnings(result)
            warning_text = " ".join(warning_texts).casefold()
            if any(
                marker in error_message
                for marker in (
                    "requires provider credentials",
                    "provider credentials",
                    "provider unavailable",
                    "upstream unavailable",
                )
            ):
                return "provider_api"
            if any(
                marker in warning_text
                for marker in (
                    "retrieval failed",
                    "provider request failed",
                    "provider unavailable",
                    "requires provider credentials",
                    "upstream unavailable",
                    "timed out",
                    "timeout",
                    "rate limit",
                    "rate_limited",
                    "invalid query",
                    "invalidqueryerror",
                    "malformed response",
                    "connection error",
                    "service unavailable",
                )
            ):
                return "provider_api"
            if code == "context_limit":
                return "context_limit"
            if code in provider_codes or code.startswith("provider_"):
                return "provider_api"
            if code in parsing_codes:
                return "response_parsing"
        return None

    # -------------------------------------------------------------------------
    @classmethod
    def build_verified_assistant_message(
        cls,
        fallback_text: str,
        *,
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
        require_verified_result: bool = False,
    ) -> str:
        if map_session is not None:
            map_message = cls.compose_map_session_message(map_session)
            if direct_result is not None:
                tool_id = direct_result.get("tool_id") or direct_result.get("tool")
                direct_message = cls.compose_direct_tool_message(
                    tool_id, {"result": direct_result}
                )
                if not direct_message.startswith("Completed "):
                    return f"{map_message} {direct_message}"
            return map_message
        if direct_result is not None:
            tool_id = direct_result.get("tool_id") or direct_result.get("tool")
            return cls.compose_direct_tool_message(tool_id, {"result": direct_result})
        tool_error = cls.extract_tool_error_message(tool_payload)
        if tool_error is not None:
            return tool_error
        if require_verified_result:
            return "I could not verify a map result for this request."
        return fallback_text or "Done."

    # -------------------------------------------------------------------------
    @staticmethod
    def build_preflight_operation_result(
        *,
        decision_state: str,
        assistant_message: str,
    ) -> ChatOperationResult:
        if decision_state == "clarify":
            return ChatOperationResult(
                kind="clarification",
                status="partial",
                message=assistant_message,
            )
        return ChatOperationResult(
            kind="rejection",
            status="failed",
            message=assistant_message,
        )

    # -------------------------------------------------------------------------
    @classmethod
    def build_verified_operation_result(
        cls,
        *,
        assistant_message: str,
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
        user_text: str,
        is_capability_question: bool,
        require_verified_result: bool = False,
    ) -> ChatOperationResult:
        warnings = cls.collect_operation_warnings(
            map_session=map_session,
            tool_payload=tool_payload,
        )
        if map_session is not None:
            map_status = cls._map_session_status(map_session)
            return ChatOperationResult(
                kind="map_session",
                status=map_status,
                message=assistant_message,
                warnings=warnings,
                direct_result=direct_result,
            )
        if direct_result is not None:
            return ChatOperationResult(
                kind="direct_answer",
                status="success",
                message=assistant_message,
                warnings=warnings,
                direct_result=direct_result,
            )
        tool_error = cls.extract_tool_error_message(tool_payload)
        if tool_error is not None:
            return ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message or tool_error,
                warnings=warnings,
            )
        if is_capability_question:
            return ChatOperationResult(
                kind="capability_catalog",
                status="success",
                message=assistant_message,
                warnings=warnings,
            )
        if require_verified_result:
            return ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message
                or "I could not verify a map result for this request.",
                warnings=warnings,
            )
        _ = user_text
        return ChatOperationResult(
            kind="direct_answer",
            status="success",
            message=assistant_message,
            warnings=warnings,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_session_status(
        map_session: MapSession,
    ) -> Literal["success", "partial", "failed"]:
        has_render_failure = any(
            " is not available" in warning or " failed (" in warning
            for warning in map_session.compliance_warnings
        )
        if has_render_failure and not map_session.overlay_collection.instances:
            return "failed"
        if has_render_failure:
            return "partial"
        return "success"

    # -------------------------------------------------------------------------
    @staticmethod
    def extract_tool_error_message(tool_payload: dict[str, Any] | None) -> str | None:
        if not is_json_object(tool_payload):
            return None
        for result in json_array(tool_payload.get("tool_results")):
            if not is_json_object(result):
                continue
            content = result.get("content")
            if not is_json_object(content) or bool(content.get("ok", True)):
                continue
            error = content.get("error")
            if is_json_object(error) and isinstance(error.get("message"), str):
                return error["message"]
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def collect_operation_warnings(
        *,
        map_session: MapSession | None,
        tool_payload: dict[str, Any] | None,
    ) -> list[str]:
        warnings: list[str] = []
        if map_session is not None:
            warnings.extend(
                warning
                for warning in map_session.compliance_warnings
                if warning.strip()
            )
        if not is_json_object(tool_payload):
            return warnings
        for result in json_array(tool_payload.get("tool_results")):
            if not is_json_object(result):
                continue
            content = result.get("content")
            if not is_json_object(content):
                continue
            data = content.get("data")
            if not is_json_object(data):
                continue
            warning_values: list[Any] = json_array(data.get("warnings"))
            for warning in warning_values:
                if (
                    isinstance(warning, str)
                    and warning.strip()
                    and warning not in warnings
                ):
                    warnings.append(warning)
        return warnings

    # -------------------------------------------------------------------------
    @classmethod
    def compose_direct_tool_message(
        cls,
        tool_id: object,
        tool_payload: dict[str, Any] | None,
    ) -> str:
        payload = json_object(tool_payload)
        if payload.get("error"):
            return str(payload["error"])
        result = payload.get("result")
        if not is_json_object(result):
            return f"Completed {cls.humanize_identifier(tool_id)}."

        nested_result = result.get("result")
        if tool_id == "location_to_coordinates":
            coordinates = result.get("coordinates")
            location = result.get("location") or cls.extract_label(
                payload.get("location")
            )
            if is_json_object(coordinates):
                latitude = coordinates.get("latitude")
                longitude = coordinates.get("longitude")
                if isinstance(latitude, (int, float)) and isinstance(
                    longitude, (int, float)
                ):
                    return (
                        f"Coordinates for {location}: {latitude:.6f}, {longitude:.6f}."
                    )
        if tool_id == "get_weather_forecast" and is_json_object(nested_result):
            current = nested_result.get("selected_forecast") or nested_result.get(
                "current"
            )
            location = result.get("location") or cls.extract_label(
                payload.get("location")
            )
            if is_json_object(current):
                temperature = current.get("temperature_2m")
                precipitation = current.get("precipitation")
                weather_time = current.get("time")
                details: list[str] = []
                if isinstance(temperature, (int, float)):
                    details.append(f"temperature {temperature:g} C")
                if isinstance(precipitation, (int, float)):
                    details.append(f"precipitation {precipitation:g} mm")
                if details:
                    suffix = (
                        f" at {weather_time}"
                        if isinstance(weather_time, str) and weather_time
                        else ""
                    )
                    return f"Weather for {location}{suffix}: {', '.join(details)}."
        return f"Completed {cls.humanize_identifier(tool_id)}."

    # -------------------------------------------------------------------------
    @classmethod
    def compose_map_session_message(cls, map_session: MapSession) -> str:
        location = map_session.resolved_location.label or "the requested location"
        basemap = cls.extract_label(map_session.basemap) or cls.humanize_identifier(
            map_session.basemap_id
        )
        instances = map_session.overlay_collection.instances
        visible_labels = [
            instance.label or cls.humanize_identifier(instance.capability_id)
            for instance in instances
            if instance.visible
        ]
        hidden_labels = [
            instance.label or cls.humanize_identifier(instance.capability_id)
            for instance in instances
            if not instance.visible
        ]
        warnings = [
            cls.humanize_warning(warning)
            for warning in map_session.compliance_warnings
            if warning.strip()
        ]

        parts = [f"Map ready for {location} using {basemap}."]
        if visible_labels:
            parts.append(f"Visible overlays: {cls.format_label_list(visible_labels)}.")
        if hidden_labels:
            parts.append(f"Hidden overlays: {cls.format_label_list(hidden_labels)}.")
        if not visible_labels and not hidden_labels:
            parts.append("No overlays are currently active.")
        if warnings:
            parts.append(
                f"Some requested map data needs attention: {' '.join(warnings)}"
            )
        return " ".join(parts)

    # -------------------------------------------------------------------------
    @staticmethod
    def extract_label(value: object) -> str | None:
        if is_json_object(value):
            label = value.get("label") or value.get("name") or value.get("id")
            if isinstance(label, str) and label.strip():
                return label.strip()
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def format_label_list(labels: list[str]) -> str:
        if len(labels) == 1:
            return f"the {labels[0]} overlay"
        if len(labels) == 2:
            return f"the {labels[0]} and {labels[1]} overlays"
        return f"the {', '.join(labels[:-1])}, and {labels[-1]} overlays"

    # -------------------------------------------------------------------------
    @classmethod
    def humanize_warning(cls, warning: str) -> str:
        message = warning.strip()
        if ":" in message:
            capability_id, detail = message.split(":", 1)
            message = f"{cls.humanize_identifier(capability_id)}: {detail.strip()}"

        replacements = {
            "TOMTOM_API_KEY": "TomTom API key",
            "WINDY_WEBCAMS_API_KEY": "Windy Webcams API key",
            "osm_default": "OpenStreetMap",
            "tomtom_traffic_flow": "TomTom Traffic Flow",
            "windy_webcams": "Windy Webcams",
        }
        for raw, readable in replacements.items():
            message = message.replace(raw, readable)
        if not message.endswith("."):
            message += "."
        return message

    # -------------------------------------------------------------------------
    @staticmethod
    def humanize_identifier(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            return "the default basemap"
        known_names = {
            "osm_default": "OpenStreetMap",
            "tomtom_traffic_flow": "TomTom Traffic Flow",
        }
        if value in known_names:
            return known_names[value]
        words = value.replace("-", "_").split("_")
        acronyms = {"osm": "OpenStreetMap", "modis": "MODIS", "viirs": "VIIRS"}
        return " ".join(
            acronyms.get(word.lower(), word.capitalize()) for word in words if word
        )
