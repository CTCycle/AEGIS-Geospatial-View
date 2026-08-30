from __future__ import annotations

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
        if not label:
            return []
        return [
            LocationSignal(
                signal_type="deictic",
                raw_value=label,
                normalized_value=label,
                latitude=float(active.get("latitude") or 0.0),
                longitude=float(active.get("longitude") or 0.0),
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
