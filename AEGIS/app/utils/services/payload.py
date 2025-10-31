from __future__ import annotations

from typing import Any
from datetime import datetime, date
from fastapi import HTTPException, status


# HELPERS
###############################################################################
def sanitize_field(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None

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
    filter_val: Any,
    country: str | None,
    city: str | None,
    address: str | None,
    use_coordinates: bool,
    latitude: Any,
    longitude: Any,
    date: str | None,
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
        
    payload: dict[str, Any] = {
        "filter": filter_val,
        "country": sanitize_field(country),
        "city": sanitize_field(city),
        "address": sanitize_field(address),
        "use_coordinates": bool(use_coordinates),        
        "coordinates": (
            {"latitude": latitude, "longitude": longitude} if use_coordinates else None
        ),
        "latitude": latitude if use_coordinates else None,
        "longitude": longitude if use_coordinates else None,       
        "date": sanitize_field(date),
        "datetime": sanitize_field(date),
    }

    return payload
