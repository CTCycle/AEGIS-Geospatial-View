from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


# HELPERS
###############################################################################
def sanitize_field(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


# -----------------------------------------------------------------------------
def sanitize_choice(value: Any) -> str | None:
    if value is None:
        return None
    normalized = sanitize_field(str(value))
    if normalized and normalized.lower() == "none":
        return None
    return normalized


# -----------------------------------------------------------------------------
def sanitize_choice_list(values: list[Any] | None) -> list[str]:
    if values is None:
        return []
    normalized_values: list[str] = []
    for value in values:
        normalized = sanitize_choice(value)
        if normalized is None:
            continue
        if normalized in normalized_values:
            continue
        normalized_values.append(normalized)
    return normalized_values


# -----------------------------------------------------------------------------
def coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


##############################################################################
def sanitize_search_payload(
    *,
    geospatial_filters: list[Any],
    map_tiles: str | None,
    country: str | None,
    city: str | None,
    address: str | None,
    use_coordinates: bool,
    latitude: Any,
    longitude: Any,
    date: str | None,
    agentic_enabled: bool,
) -> dict[str, Any]:
    # If coordinates mode is on, lat/lon must be present
    if use_coordinates and (latitude is None or longitude is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Coordinates must be present in coordinates search mode.",
        )

    # If coordinates mode is off, require at least some textual location input
    if not use_coordinates and not any([address, city, country]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide an address/city/country or enable coordinates.",
        )

    sanitized_filters = sanitize_choice_list(geospatial_filters)
    selected_tiles = sanitize_choice(map_tiles)

    payload: dict[str, Any] = {
        "filters": sanitized_filters,
        "geospatial_filter": sanitized_filters,
        "map_tiles": selected_tiles,
        "country": sanitize_field(country),
        "city": sanitize_field(city),
        "address": sanitize_field(address),
        "use_coordinates": bool(use_coordinates),
        "latitude": latitude if use_coordinates else None,
        "longitude": longitude if use_coordinates else None,
        "date": sanitize_field(date),
        "datetime": sanitize_field(date),
        "agentic_enabled": bool(agentic_enabled),
    }

    return payload
