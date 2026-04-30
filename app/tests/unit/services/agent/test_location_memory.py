from __future__ import annotations

from server.services.agent.location_memory import LocationMemoryService


def test_resolve_explicit_reference_with_memory() -> None:
    service = LocationMemoryService()
    snapshot = {
        "active_location": {
            "label": "Colosseum, Rome",
            "latitude": 41.8902,
            "longitude": 12.4922,
        }
    }
    signals = service.resolve_explicit_references("show traffic there now", snapshot)
    assert len(signals) == 1
    assert signals[0].signal_type == "deictic"


def test_build_memory_snapshot_defaults() -> None:
    service = LocationMemoryService()
    snapshot = service.build_memory_snapshot(None)
    assert snapshot["location_slots"] == []
