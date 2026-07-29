from __future__ import annotations

from typing import Any

from server.domain.extraction.models import TurnParseResult

###############################################################################
class ToolArgumentBuilder:

    # -------------------------------------------------------------------------
    def build_location_arguments(
        self,
        turn: TurnParseResult,
        memory_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        for signal in turn.location_signals:
            if signal.latitude is not None and signal.longitude is not None:
                return {
                    "latitude": signal.latitude,
                    "longitude": signal.longitude,
                    "location": signal.normalized_value or signal.raw_value,
                }
            if signal.normalized_value or signal.raw_value:
                return {"location": signal.normalized_value or signal.raw_value}
        active = (memory_snapshot or {}).get("active_location")
        if isinstance(active, dict):
            latitude = active.get("latitude")
            longitude = active.get("longitude")
            if isinstance(latitude, int | float) and isinstance(longitude, int | float):
                return {
                    "latitude": latitude,
                    "longitude": longitude,
                    "location": active.get("label"),
                }
        if turn.map_target:
            return {"location": turn.map_target}
        return {"query": turn.user_text}

    # -------------------------------------------------------------------------
    def build_bbox_arguments(
        self,
        turn: TurnParseResult,
        memory_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        memory = memory_snapshot or {}
        for candidate in (
            memory.get("bbox"),
            (memory.get("viewport") or {}).get("bbox")
            if isinstance(memory.get("viewport"), dict)
            else None,
            (memory.get("active_visualization") or {}).get("bounds")
            if isinstance(memory.get("active_visualization"), dict)
            else None,
        ):
            if (
                isinstance(candidate, list)
                and len(candidate) == 4
                and all(isinstance(value, int | float) for value in candidate)
            ):
                return {"bbox": candidate}
        return self.build_location_arguments(turn, memory_snapshot)

    # -------------------------------------------------------------------------
    @staticmethod
    def build_temporal_arguments(turn: TurnParseResult) -> dict[str, Any]:
        temporal = turn.temporal_signal
        if temporal.mode == "none":
            return {}
        arguments: dict[str, Any] = {"temporal_mode": temporal.mode}
        if temporal.raw_text:
            arguments["time"] = temporal.raw_text
        if temporal.reference_time_iso:
            arguments["reference_time_iso"] = temporal.reference_time_iso
        return arguments

    # -------------------------------------------------------------------------
    def build_capability_arguments(
        self,
        capability_id: str,
        turn: TurnParseResult,
        memory_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        location_capabilities = {
            "get_air_quality_forecast",
            "get_nearby_poi",
            "get_weather_forecast",
            "location_to_coordinates",
        }
        arguments = (
            self.build_location_arguments(turn, memory_snapshot)
            if capability_id in location_capabilities
            else self.build_bbox_arguments(turn, memory_snapshot)
        )
        arguments.update(self.build_temporal_arguments(turn))
        if capability_id == "get_nearby_poi":
            arguments["query"] = turn.entity_target or turn.user_text
        elif capability_id == "location_to_coordinates":
            arguments["query"] = arguments.get("location") or turn.user_text
        return {key: value for key, value in arguments.items() if value is not None}
