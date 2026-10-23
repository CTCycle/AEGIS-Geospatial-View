"""Deterministic geodesic measurements over resolved locations."""

from __future__ import annotations

import time
from itertools import combinations
from typing import Any

from server.common.identifiers import location_ref_matches
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.services.agent.tool_definitions import MeasureGeospatialInput
from server.services.geospatial.land_mask import MASK_SOURCE, country_at
from server.services.geospatial.spatial_constraints import (
    geodesic_bbox_area_km2,
    geodesic_distance_m,
    geodesic_inverse,
)

GEODESIC_METHOD = "WGS84 ellipsoid geodesic (pyproj)"
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

###############################################################################
class MeasureToolHandler:

    # -------------------------------------------------------------------------
    async def measure(
        self,
        request: MeasureGeospatialInput,
        state: AgentRunState,
    ) -> ToolResult:
        started = time.perf_counter()
        locations: list[tuple[str, ResolvedLocation]] = []
        for ref in dict.fromkeys(request.location_refs):
            match = next(
                (
                    (str(key), location)
                    for key, location in state.location_refs.items()
                    if location_ref_matches(ref, str(key), location.label)
                ),
                None,
            )
            if match is None:
                return _failure(
                    f"'{ref}' is not a resolved location; resolve it first and "
                    "pass its target_id.",
                    started,
                )
            locations.append(match)

        if request.operation == "distance":
            if len(locations) < 2:
                return _failure("distance needs at least two locations.", started)
            measurements = [_distance(first, second) for first, second in combinations(locations, 2)]
            first = measurements[0]
            summary = (
                f"Geodesic distance from {first['from_label']} to {first['to_label']}: "
                f"{first['distance_km']} km ({first['distance_mi']} mi)."
                if len(measurements) == 1
                else f"Computed {len(measurements)} pairwise geodesic distances."
            )
            method = GEODESIC_METHOD
        elif request.operation == "extent":
            measurements = [_extent(key, location) for key, location in locations]
            summary = f"Measured the extent of {len(measurements)} location(s)."
            method = GEODESIC_METHOD
        else:
            measurements = [
                {
                    "location_ref": key,
                    "label": location.label,
                    "country_iso2": country_at(location.longitude, location.latitude),
                }
                for key, location in locations
            ]
            summary = "; ".join(
                f"{item['label']}: {item['country_iso2'] or 'no country (sea or outside the shapes)'}"
                for item in measurements
            )
            method = f"point in simplified {MASK_SOURCE} country polygons"
        return ToolResult(
            call_id="handler-call",
            tool_name="measure_geospatial",
            status="success",
            summary=summary,
            data={
                "operation": request.operation,
                "measurements": measurements,
                "method": method,
            },
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000))
            ),
        )

###############################################################################
def _distance(
    first: tuple[str, ResolvedLocation], second: tuple[str, ResolvedLocation]
) -> dict[str, Any]:
    (first_key, a), (second_key, b) = first, second
    metres, bearing = geodesic_inverse(a.latitude, a.longitude, b.latitude, b.longitude)
    return {
        "from": first_key,
        "from_label": a.label,
        "to": second_key,
        "to_label": b.label,
        "distance_km": round(metres / 1000.0, 1),
        "distance_mi": round(metres / 1609.344, 1),
        "initial_bearing_deg": round(bearing, 1),
        "bearing_compass": _COMPASS[round(bearing / 45.0) % 8],
        "between": "resolved centre points",
    }

###############################################################################
def _extent(key: str, location: ResolvedLocation) -> dict[str, Any]:
    measurement: dict[str, Any] = {
        "location_ref": key,
        "label": location.label,
        "centre": [location.longitude, location.latitude],
    }
    bbox = location.bbox
    if not bbox or len(bbox) != 4:
        measurement["note"] = "The location is a point without a resolved extent."
        return measurement
    west, south, east, north = (float(value) for value in bbox)
    middle_latitude = (south + north) / 2
    middle_longitude = (west + east) / 2
    measurement.update(
        {
            "bbox": [west, south, east, north],
            "width_km": round(
                geodesic_distance_m(middle_latitude, west, middle_latitude, east) / 1000.0, 1
            ),
            "height_km": round(
                geodesic_distance_m(south, middle_longitude, north, middle_longitude) / 1000.0, 1
            ),
            "bbox_area_km2": round(geodesic_bbox_area_km2([west, south, east, north]), 1),
            "note": "Measured on the bounding box, not the administrative boundary.",
        }
    )
    return measurement

###############################################################################
def _failure(message: str, started: float) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="measure_geospatial",
        status="failed",
        summary=message,
        error=ToolExecutionError(
            error_type="semantic_validation",
            code="invalid_measurement",
            message=message,
            retryable=False,
            recovery="correct_arguments",
        ),
        metadata=ToolExecutionMetadata(
            duration_ms=max(0, int((time.perf_counter() - started) * 1000))
        ),
    )


__all__ = ["MeasureToolHandler"]
