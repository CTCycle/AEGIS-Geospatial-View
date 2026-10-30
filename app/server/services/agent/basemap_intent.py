from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from server.common.typing import json_object

_DEFAULT_BASEMAP_ID = "osm_default"
# Terms too generic to signal a basemap choice on their own.
_GENERIC_TERMS = frozenset(
    {"light", "clean", "places", "presentation", "contrast", "roads", "street", "vector"}
)

###############################################################################
def basemap_label(item: Mapping[str, Any]) -> str:
    metadata = json_object(item.get("metadata"))
    return str(metadata.get("label") or item.get("name") or item.get("id") or "").strip()

###############################################################################
def basemap_terms(item: Mapping[str, Any]) -> list[str]:
    """Return the manifest keywords and map-type tags describing a basemap."""

    metadata = json_object(item.get("metadata"))
    terms: list[str] = []
    for key in ("keywords", "map_type_tags"):
        raw = metadata.get(key)
        if isinstance(raw, list):
            terms.extend(str(term).strip().casefold() for term in raw if str(term).strip())
    return list(dict.fromkeys(terms))

###############################################################################
def basemap_descriptions(basemaps: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Map each basemap ID to a short label + keyword description for the model."""

    descriptions: dict[str, str] = {}
    for item in basemaps:
        basemap_id = str(item.get("id") or "").strip()
        if not basemap_id:
            continue
        label = basemap_label(item)
        terms = ", ".join(basemap_terms(item))
        descriptions[basemap_id] = f"{label} ({terms})" if terms else label
    return descriptions

###############################################################################
def match_requested_basemap(
    user_message: str, basemaps: Iterable[Mapping[str, Any]]
) -> str | None:
    """Return the one non-default basemap the message names, or None if unclear."""

    words = set(re.findall(r"\w+", user_message.casefold()))
    matched: list[str] = []
    for item in basemaps:
        basemap_id = str(item.get("id") or "").strip()
        if not basemap_id or basemap_id == _DEFAULT_BASEMAP_ID:
            continue
        terms = {term for term in basemap_terms(item) if term not in _GENERIC_TERMS}
        if terms & words:
            matched.append(basemap_id)
    return matched[0] if len(matched) == 1 else None
