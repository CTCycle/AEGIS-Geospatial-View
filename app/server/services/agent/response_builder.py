from __future__ import annotations

from typing import Any

from server.domain.chat import ChatOperationResult
from server.domain.geographics import MapSession


class AgentResponseBuilder:
    @classmethod
    def should_build_fallback_map(
        cls,
        *,
        task_class: str,
        requires_location: bool,
        location_signals: list[object],
        tool_payload: dict[str, Any] | None,
    ) -> bool:
        if task_class != "map_search":
            return False
        if not requires_location and not location_signals:
            return False
        if not isinstance(tool_payload, dict):
            return True
        if cls.tool_payload_has_error(tool_payload):
            return False
        catalog_only_tools = {
            "list_geospatial_capabilities",
            "describe_geospatial_capability",
        }
        for tool_call in tool_payload.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            tool_name = tool_call.get("name")
            if isinstance(tool_name, str) and tool_name not in catalog_only_tools:
                return False
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict):
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            if data.get("map_session") or data.get("direct_result") or data.get(
                "capability_selection"
            ):
                return False
        return True

    @staticmethod
    def tool_payload_has_error(tool_payload: dict[str, Any] | None) -> bool:
        if not isinstance(tool_payload, dict):
            return False
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if isinstance(content, dict) and content.get("ok") is False:
                return True
        return False

    @classmethod
    def build_verified_assistant_message(
        cls,
        fallback_text: str,
        *,
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
    ) -> str:
        if map_session is not None:
            return cls.compose_map_session_message(map_session.model_dump(mode="json"))
        if direct_result is not None:
            tool_id = direct_result.get("tool_id") or direct_result.get("tool")
            return cls.compose_direct_tool_message(tool_id, {"result": direct_result})
        tool_error = cls.extract_tool_error_message(tool_payload)
        if tool_error is not None:
            return tool_error
        return fallback_text or "Done."

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
    ) -> ChatOperationResult:
        warnings = cls.collect_operation_warnings(
            map_session=map_session,
            tool_payload=tool_payload,
        )
        if map_session is not None:
            return ChatOperationResult(
                kind="map_session",
                status="success",
                message=assistant_message,
                warnings=warnings,
                map_session=map_session,
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
        _ = user_text
        return ChatOperationResult(
            kind="direct_answer",
            status="success",
            message=assistant_message,
            warnings=warnings,
        )

    @staticmethod
    def extract_tool_error_message(tool_payload: dict[str, Any] | None) -> str | None:
        if not isinstance(tool_payload, dict):
            return None
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict) or bool(content.get("ok", True)):
                continue
            error = content.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return error["message"]
        return None

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
                if isinstance(warning, str) and warning.strip()
            )
        if not isinstance(tool_payload, dict):
            return warnings
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict):
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            for warning in data.get("warnings") or []:
                if (
                    isinstance(warning, str)
                    and warning.strip()
                    and warning not in warnings
                ):
                    warnings.append(warning)
        return warnings

    @classmethod
    def compose_direct_tool_message(
        cls,
        tool_id: object,
        tool_payload: dict[str, Any] | None,
    ) -> str:
        if isinstance(tool_payload, dict) and tool_payload.get("error"):
            return str(tool_payload["error"])
        result = tool_payload.get("result") if isinstance(tool_payload, dict) else None
        if not isinstance(result, dict):
            return f"Completed {cls.humanize_identifier(tool_id)}."

        nested_result = result.get("result")
        if tool_id == "location_to_coordinates":
            coordinates = result.get("coordinates")
            location = result.get("location") or cls.extract_label(
                tool_payload.get("location")
            )
            if isinstance(coordinates, dict):
                latitude = coordinates.get("latitude")
                longitude = coordinates.get("longitude")
                if isinstance(latitude, (int, float)) and isinstance(
                    longitude, (int, float)
                ):
                    return f"Coordinates for {location}: {latitude:.6f}, {longitude:.6f}."
        if tool_id == "get_weather_forecast" and isinstance(nested_result, dict):
            current = nested_result.get("selected_forecast") or nested_result.get(
                "current"
            )
            location = result.get("location") or cls.extract_label(
                tool_payload.get("location")
            )
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
                    suffix = (
                        f" at {weather_time}"
                        if isinstance(weather_time, str) and weather_time
                        else ""
                    )
                    return f"Weather for {location}{suffix}: {', '.join(details)}."
        return f"Completed {cls.humanize_identifier(tool_id)}."

    @classmethod
    def compose_map_session_message(cls, map_payload: dict[str, Any]) -> str:
        location = cls.extract_label(map_payload.get("resolved_location"))
        if location is None:
            location = "the requested location"
        basemap = cls.extract_label(map_payload.get("basemap")) or cls.humanize_identifier(
            map_payload.get("basemap_id")
        )
        overlay_labels = cls.extract_overlay_labels(map_payload)
        warnings = [
            cls.humanize_warning(warning)
            for warning in map_payload.get("compliance_warnings") or []
            if isinstance(warning, str) and warning.strip()
        ]

        parts = [f"Map ready for {location} using {basemap}."]
        if overlay_labels:
            parts.append(f"I added {cls.format_label_list(overlay_labels)}.")
        else:
            parts.append("No overlays were added.")
        if warnings:
            parts.append(f"Some requested map data needs attention: {' '.join(warnings)}")
        return " ".join(parts)

    @classmethod
    def extract_overlay_labels(cls, map_payload: dict[str, Any]) -> list[str]:
        overlays = map_payload.get("overlays")
        if isinstance(overlays, list):
            labels = [cls.extract_label(overlay) for overlay in overlays]
            human_labels = [label for label in labels if label]
            if human_labels:
                return human_labels

        overlay_ids = map_payload.get("overlay_ids")
        if not isinstance(overlay_ids, list):
            return []
        return [
            cls.humanize_identifier(overlay_id)
            for overlay_id in overlay_ids
            if overlay_id
        ]

    @staticmethod
    def extract_label(value: object) -> str | None:
        if isinstance(value, dict):
            label = value.get("label") or value.get("name") or value.get("id")
            if isinstance(label, str) and label.strip():
                return label.strip()
        return None

    @staticmethod
    def format_label_list(labels: list[str]) -> str:
        if len(labels) == 1:
            return f"the {labels[0]} overlay"
        if len(labels) == 2:
            return f"the {labels[0]} and {labels[1]} overlays"
        return f"the {', '.join(labels[:-1])}, and {labels[-1]} overlays"

    @classmethod
    def humanize_warning(cls, warning: str) -> str:
        message = warning.strip()
        if ":" in message:
            capability_id, detail = message.split(":", 1)
            message = f"{cls.humanize_identifier(capability_id)}: {detail.strip()}"

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
    def humanize_identifier(value: object) -> str:
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
        return " ".join(
            acronyms.get(word.lower(), word.capitalize()) for word in words if word
        )
