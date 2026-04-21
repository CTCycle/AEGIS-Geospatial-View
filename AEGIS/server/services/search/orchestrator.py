from __future__ import annotations

from datetime import UTC, datetime

from AEGIS.server.domain.geographics import LocationSearchRequest, MapSession
from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry


class LocationSearchOrchestrator:
    def __init__(self, *, capability_registry: CapabilityRegistry | None = None) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()

    async def execute(self, payload: LocationSearchRequest) -> MapSession:
        self.capability_registry.load_capabilities()
        return MapSession(
            session_id=f"map-{int(datetime.now(UTC).timestamp())}",
            resolved_location=payload.resolved_location,
            basemap_id=payload.basemap_id,
            overlay_ids=list(payload.overlay_ids),
            viewport=payload.viewport,
            payload={
                "intent_id": payload.intent_id,
                "time_mode": payload.time_mode,
                "presentation": payload.presentation.model_dump(mode="json"),
            },
        )
