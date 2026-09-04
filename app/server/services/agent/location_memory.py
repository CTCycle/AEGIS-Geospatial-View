from __future__ import annotations

import math
from typing import Any

from server.common.typing import is_json_array, is_json_object, json_array, json_object

from server.domain.agent.decision import ResolvedLocation
from server.contracts.extraction import LocationSignal, NormalizedAction


###############################################################################
class LocationMemoryService:
    # -------------------------------------------------------------------------
    def build_memory_snapshot(
        self, last_assistant_payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        if last_assistant_payload is None:
            return {"location_slots": [], "active_location": None}
        snapshot = json_object(last_assistant_payload.get("memory_snapshot"))
        return {
            "location_slots": json_array(snapshot.get("location_slots")),
            "active_location": snapshot.get("active_location"),
        }

    # -------------------------------------------------------------------------
    def resolve_explicit_references(
        self,
        signals: list[LocationSignal],
        snapshot: dict[str, Any],
    ) -> list[LocationSignal]:
        if not any(signal.signal_type == "deictic" for signal in signals):
            return []
        active = json_object(snapshot.get("active_location"))
        if not active:
            return []
        label = str(active.get("label") or "").strip()
        latitude = _finite_number(active.get("latitude"), minimum=-90.0, maximum=90.0)
        longitude = _finite_number(
            active.get("longitude"), minimum=-180.0, maximum=180.0
        )
        if not label or latitude is None or longitude is None:
            return []
        return [
            LocationSignal(
                signal_type="deictic",
                raw_value=label,
                normalized_value=label,
                latitude=latitude,
                longitude=longitude,
                confidence=0.85,
                source="memory",
            )
        ]

    # -------------------------------------------------------------------------
    def update_memory_snapshot(
        self,
        snapshot: dict[str, Any],
        resolved_location: ResolvedLocation,
        action: NormalizedAction,
    ) -> dict[str, Any]:
        slots = json_array(snapshot.get("location_slots"))
        location_payload = {
            "label": resolved_location.label,
            "latitude": resolved_location.latitude,
            "longitude": resolved_location.longitude,
            "country": resolved_location.country,
            "city": resolved_location.city,
            "address": resolved_location.address,
            "location_type": resolved_location.location_type,
            "location_class": resolved_location.location_class,
            "bbox": list(resolved_location.bbox)
            if is_json_array(resolved_location.bbox)
            else None,
            "bbox_source": resolved_location.bbox_source,
            "source": resolved_location.source,
            "confidence": resolved_location.confidence,
            "action_id": action.action_id,
            "hierarchy": (
                resolved_location.hierarchy.model_dump(mode="json")
                if resolved_location.hierarchy is not None
                else None
            ),
        }
        slots = [
            entry
            for entry in slots
            if not is_json_object(entry)
            or entry.get("label") != resolved_location.label
        ]
        slots.insert(0, location_payload)
        return {
            "location_slots": slots[:8],
            "active_location": location_payload,
        }


def _finite_number(
    value: object, *, minimum: float, maximum: float
) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not minimum <= number <= maximum:
        return None
    return number
