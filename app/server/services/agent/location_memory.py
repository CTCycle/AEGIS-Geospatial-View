from __future__ import annotations

import re

from server.domain.agent.decision import ResolvedLocation
from server.domain.extraction.models import LocationSignal, NormalizedIntent

###############################################################################
class LocationMemoryService:
    REFERENCE_PATTERN = re.compile(r"\b(there|that place|same place|same area|there now)\b", re.IGNORECASE)

    def build_memory_snapshot(self, last_assistant_payload: dict | None) -> dict:
        if not isinstance(last_assistant_payload, dict):
            return {"location_slots": [], "active_location": None}
        snapshot = last_assistant_payload.get("memory_snapshot")
        if isinstance(snapshot, dict):
            return {
                "location_slots": list(snapshot.get("location_slots") or []),
                "active_location": snapshot.get("active_location"),
            }
        return {"location_slots": [], "active_location": None}

    def resolve_explicit_references(self, user_text: str, snapshot: dict) -> list[LocationSignal]:
        if not self.REFERENCE_PATTERN.search(user_text):
            return []
        active = snapshot.get("active_location") if isinstance(snapshot, dict) else None
        if not isinstance(active, dict):
            return []
        label = str(active.get("label") or "").strip()
        if not label:
            return []
        return [
            LocationSignal(
                signal_type="deictic",
                raw_value=label,
                normalized_value=label,
                latitude=float(active.get("latitude")),
                longitude=float(active.get("longitude")),
                confidence=0.85,
                source="memory",
            )
        ]

    def update_memory_snapshot(
        self,
        snapshot: dict,
        resolved_location: ResolvedLocation,
        intent: NormalizedIntent,
    ) -> dict:
        slots = list(snapshot.get("location_slots") or []) if isinstance(snapshot, dict) else []
        location_payload = {
            "label": resolved_location.label,
            "latitude": resolved_location.latitude,
            "longitude": resolved_location.longitude,
            "country": resolved_location.country,
            "city": resolved_location.city,
            "address": resolved_location.address,
            "intent_id": intent.intent_id,
        }
        slots = [entry for entry in slots if not isinstance(entry, dict) or entry.get("label") != resolved_location.label]
        slots.insert(0, location_payload)
        return {
            "location_slots": slots[:8],
            "active_location": location_payload,
        }
