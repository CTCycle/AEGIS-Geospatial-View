from __future__ import annotations

from server.services.vector.manifest_preparation import ManifestPreparationService


def test_manifest_preparation_includes_runtime_metadata() -> None:
    service = ManifestPreparationService()
    entry = {
        "id": "x",
        "name": "X",
        "provider": "fallback",
        "type": "tile",
        "description": "desc",
        "capabilities": ["map"],
        "coverage": "global",
        "metadata": {
            "action_tags": ["map"],
            "task_tags": ["map"],
            "search_examples": ["show map"],
            "location_dependency": "location-specific",
            "constraints": "none",
        },
    }
    prepared = service.prepare_entry(entry, "tools", runtime_profile={"supports_map": True})
    assert "Runtime supports map" in prepared.text
