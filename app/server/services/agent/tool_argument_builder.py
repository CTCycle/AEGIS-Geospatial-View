from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

from typing import Any

from server.contracts.extraction import TurnParseResult
from server.services.geospatial.capability_registry import CapabilityRegistry


###############################################################################
class ToolArgumentBuilder:
    # -------------------------------------------------------------------------
    def __init__(self, capability_registry: CapabilityRegistry | None = None) -> None:
        self.capability_registry = capability_registry

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
        if is_json_object(active):
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
        if self._has_explicit_location_signal(turn):
            return self.build_location_arguments(turn, memory_snapshot)
        memory = memory_snapshot or {}
        for candidate in (
            memory.get("bbox"),
            json_object(memory.get("viewport")).get("bbox"),
            json_object(memory.get("active_visualization")).get("bounds"),
        ):
            if (
                is_json_array(candidate)
                and len(candidate) == 4
                and all(isinstance(value, int | float) for value in candidate)
            ):
                return {"bbox": candidate}
        return self.build_location_arguments(turn, memory_snapshot)

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_explicit_location_signal(turn: TurnParseResult) -> bool:
        for signal in turn.location_signals:
            if signal.signal_type == "deictic":
                continue
            if str(signal.raw_value or "").strip():
                return True
        return False

    # -------------------------------------------------------------------------
    @staticmethod
    def build_temporal_arguments(turn: TurnParseResult) -> dict[str, Any]:
        temporal = turn.temporal_signal
        if temporal.mode == "none":
            return {}
        arguments: dict[str, Any] = {"temporal_mode": temporal.mode}
        # Current-mode requests do not need a free-form time argument.  The
        # parser can occasionally place the remainder of a compound request
        # in raw_text (for example, "show the weather there"); forwarding
        # that text to a provider makes the tool call look temporal even
        # though no temporal constraint was requested.  Forecast and
        # historical handlers use the phrase to select the requested slice.
        if temporal.mode in {"forecast", "historical"} and temporal.raw_text:
            arguments["time"] = temporal.raw_text
        if temporal.reference_time_iso:
            arguments["reference_time_iso"] = temporal.reference_time_iso
        if temporal.start_time_iso:
            arguments["start_time_iso"] = temporal.start_time_iso
        if temporal.end_time_iso:
            arguments["end_time_iso"] = temporal.end_time_iso
        if temporal.granularity != "none":
            arguments["temporal_granularity"] = temporal.granularity
        if temporal.aggregation != "none":
            arguments["aggregation"] = temporal.aggregation
        return arguments

    # -------------------------------------------------------------------------
    def build_capability_arguments(
        self,
        capability_id: str,
        turn: TurnParseResult,
        memory_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        capability = (
            self.capability_registry.get_capability(capability_id)
            if self.capability_registry is not None
            else {}
        ) or {}
        metadata = capability.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        is_direct = (
            str(capability.get("type") or "").casefold() == "direct-tool"
            or str(metadata.get("retrieval_mode") or "").casefold() == "direct"
        )
        arguments = (
            self.build_location_arguments(turn, memory_snapshot)
            if is_direct
            else self.build_bbox_arguments(turn, memory_snapshot)
        )
        arguments.update(self.build_temporal_arguments(turn))
        if capability and str(capability.get("type") or "").casefold() == "direct-tool":
            if turn.entity_target:
                arguments["query"] = turn.entity_target
            elif turn.poi_categories:
                arguments["query"] = ", ".join(turn.poi_categories)
        return {key: value for key, value in arguments.items() if value is not None}
