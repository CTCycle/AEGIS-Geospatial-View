from __future__ import annotations

from typing import Any

from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.common.constants import MAP_SEARCH_STATUS_MESSAGE


def build_request_context(payload: LocationSearchRequest) -> dict[str, Any]:
    return {
        "user": None,
        "country": payload.country,
        "city": payload.city,
        "address": payload.address,
        "longitude": payload.longitude,
        "latitude": payload.latitude,
        "overlay_ids": list(payload.overlay_ids),
        "semantic_filters": list(payload.semantic_filters),
        "basemap_id": payload.basemap_id,
    }


def build_search_response(
    *, search_payload: dict[str, Any], map_session: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status_message": MAP_SEARCH_STATUS_MESSAGE,
        "payload": search_payload,
        "map_session": map_session,
        "compliance_warnings": map_session.get("compliance_warnings", []),
    }
