from __future__ import annotations

from typing import Any


def translate_overlay_ids_to_filters(
    overlay_ids: list[str],
    overlays_manifest: list[dict[str, Any]],
) -> list[str]:
    lookup = {str(item.get("id")): item for item in overlays_manifest}
    filters: list[str] = []
    for overlay_id in overlay_ids:
        entry = lookup.get(overlay_id)
        if entry is None:
            continue
        metadata = dict(entry.get("metadata") or {})
        if str(entry.get("type") or "").lower() == "legacy-image":
            source_layer = metadata.get("source_layer_id")
            if isinstance(source_layer, str) and source_layer.strip():
                filters.append(source_layer)
                continue
        filters.append(overlay_id)
    return list(dict.fromkeys(filters))
