"""Shared, provider-neutral spatial scope validation and predicates."""

from __future__ import annotations

import math
from typing import Any, Iterable, cast

from pyproj import Geod, Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform


class SpatialConstraintError(ValueError):
    """Raised when a requested scope or geometry cannot be trusted."""


_GEOD = Geod(ellps="WGS84")


def normalize_bbox(value: Iterable[object]) -> list[float]:
    """Normalize a bbox to [west, south, east, north] without hiding wraps."""

    values = list(value)
    if len(values) != 4 or any(
        not isinstance(item, (int, float)) or isinstance(item, bool) for item in values
    ):
        raise SpatialConstraintError("Bounding boxes require four numeric values.")
    numeric_values = cast(list[int | float], values)
    west, south, east, north = (float(item) for item in numeric_values)
    if any(not math.isfinite(item) for item in (west, south, east, north)):
        raise SpatialConstraintError("Bounding box coordinates must be finite.")
    if not -90 <= south <= north <= 90:
        raise SpatialConstraintError("Bounding box latitude range is invalid.")
    if not -180 <= west <= 180 or not -180 <= east <= 180:
        raise SpatialConstraintError("Bounding box longitude range is invalid.")
    if west > east and (west < 150 or east > -150):
        raise SpatialConstraintError("Bounding box longitude order is invalid.")
    # west > east is retained as an explicit antimeridian crossing.
    if west == east and south != north:
        raise SpatialConstraintError("A non-degenerate bbox cannot have equal longitudes.")
    return [west, south, east, north]


def validate_point(latitude: object, longitude: object) -> tuple[float, float]:
    """Validate a WGS84 point and return it as (latitude, longitude)."""

    if any(
        not isinstance(item, (int, float)) or isinstance(item, bool)
        for item in (latitude, longitude)
    ):
        raise SpatialConstraintError("Coordinates must be numeric.")
    latitude_value = float(cast(int | float, latitude))
    longitude_value = float(cast(int | float, longitude))
    if not math.isfinite(latitude_value) or not math.isfinite(longitude_value):
        raise SpatialConstraintError("Coordinates must be finite.")
    if not -90 <= latitude_value <= 90 or not -180 <= longitude_value <= 180:
        raise SpatialConstraintError("Coordinates are outside EPSG:4326 bounds.")
    return latitude_value, longitude_value


def validate_geojson_geometry(geometry: object) -> dict[str, Any]:
    """Reject malformed or invalid GeoJSON geometry before map assembly."""

    if not isinstance(geometry, dict):
        raise SpatialConstraintError("GeoJSON geometry is missing its type.")
    geometry_object = cast(dict[str, Any], geometry)
    if not isinstance(geometry_object.get("type"), str):
        raise SpatialConstraintError("GeoJSON geometry is missing its type.")
    try:
        parsed = shape(geometry_object)
    except Exception as exc:
        raise SpatialConstraintError("GeoJSON geometry could not be parsed.") from exc
    if parsed.is_empty or not parsed.is_valid:
        raise SpatialConstraintError("GeoJSON geometry is empty or invalid.")
    return geometry_object


def geodesic_distance_m(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    """Return WGS84 geodesic distance in metres."""

    first = validate_point(first_latitude, first_longitude)
    second = validate_point(second_latitude, second_longitude)
    _azimuth_a, _azimuth_b, distance = _GEOD.inv(first[1], first[0], second[1], second[0])
    return float(distance)


def feature_matches_constraint(
    feature: object,
    *,
    relationship: str,
    reference_geometry: dict[str, Any] | None = None,
    reference_point: tuple[float, float] | None = None,
    distance_m: float | None = None,
) -> bool:
    """Apply a containment or distance predicate to one GeoJSON feature."""

    feature_object = cast(dict[str, Any], feature) if isinstance(feature, dict) else {}
    geometry: object = feature_object.get("geometry")
    if not isinstance(geometry, dict):
        return False
    geometry_object = cast(dict[str, Any], geometry)
    try:
        candidate = shape(validate_geojson_geometry(geometry_object))
    except SpatialConstraintError:
        return False
    if relationship in {"in", "at", "inside", "within"}:
        if reference_geometry is None:
            return False
        return candidate.within(shape(validate_geojson_geometry(reference_geometry)))
    if relationship in {"near", "around", "within_distance"}:
        if reference_point is None or distance_m is None or distance_m < 0:
            return False
        latitude, longitude = validate_point(*reference_point)
        if candidate.geom_type == "Point":
            point = cast(Any, candidate)
            nearest_latitude, nearest_longitude = validate_point(point.y, point.x)
            return (
                geodesic_distance_m(
                    latitude,
                    longitude,
                    nearest_latitude,
                    nearest_longitude,
                )
                <= distance_m
            )
        # Project around the reference point with an azimuthal equidistant CRS.
        # Distances from the projection origin are metres, so lines and areas
        # are tested by their nearest geometry rather than by a centroid or
        # representative point that could be far from a nearby edge.
        try:
            projection = Transformer.from_crs(
                "EPSG:4326",
                (
                    f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} "
                    "+datum=WGS84 +units=m +no_defs"
                ),
                always_xy=True,
            )
            projected = transform(projection.transform, candidate)
            return projected.distance(Point(0.0, 0.0)) <= distance_m
        except Exception:
            return False
    if relationship == "visible_area":
        return reference_geometry is not None and candidate.intersects(
            shape(validate_geojson_geometry(reference_geometry))
        )
    raise SpatialConstraintError(f"Unsupported spatial relationship: {relationship}")
