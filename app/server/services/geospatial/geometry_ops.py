"""Bounded WGS84 geometry operations over normalized evidence records.

Records are GeoJSON features or normalized point records with top-level
``latitude``/``longitude``. Areas and perimeters are geodesic on the WGS84
ellipsoid; buffers are built in a local azimuthal-equidistant projection
around each geometry so a distance in kilometres stays a true distance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeGuard, cast

import shapely
from pyproj import CRS, Geod, Transformer
from shapely import STRtree
from shapely.errors import GEOSException
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from server.common.typing import is_json_object

GEOD = Geod(ellps="WGS84")
MAX_GEOMETRY_RECORDS = 5_000
MAX_TOTAL_VERTICES = 250_000
MAX_BUFFER_KM = 500.0
MAX_ATTACHED_FIELDS = 12
POLYGONAL = frozenset({"Polygon", "MultiPolygon"})


###############################################################################
class GeometryOperationError(ValueError):
    """A geometry operation cannot run on the given records."""


###############################################################################
def record_geometry(item: Any) -> BaseGeometry | None:
    """Shapely geometry of a GeoJSON feature or a normalized point record."""

    if not is_json_object(item):
        return None
    geometry = item.get("geometry")
    if is_json_object(geometry):
        try:
            parsed = shape(geometry)
        except (ValueError, TypeError, KeyError, AttributeError, GEOSException):
            return None
        return None if parsed.is_empty else parsed
    for source in (item, item.get("properties")):
        if not is_json_object(source):
            continue
        latitude, longitude = source.get("latitude"), source.get("longitude")
        if (
            isinstance(latitude, int | float) and isinstance(longitude, int | float)
            and not isinstance(latitude, bool) and not isinstance(longitude, bool)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180
        ):
            return Point(float(longitude), float(latitude))
    return None


###############################################################################
def is_polygonal(geometry: BaseGeometry | None) -> TypeGuard[BaseGeometry]:
    return geometry is not None and geometry.geom_type in POLYGONAL


###############################################################################
def geodesic_area_perimeter_km(geometry: BaseGeometry) -> tuple[float, float]:
    """Geodesic area (km²) and perimeter (km) of a geometry on WGS84."""

    area_m2, perimeter_m = GEOD.geometry_area_perimeter(geometry)  # pyright: ignore[reportUnknownMemberType]
    return abs(area_m2) / 1_000_000.0, perimeter_m / 1000.0


###############################################################################
def buffer_km(geometry: BaseGeometry, distance_km: float) -> BaseGeometry:
    """Buffer by a true distance using a projection centred on the geometry."""

    if not 0 < distance_km <= MAX_BUFFER_KM:
        raise GeometryOperationError(f"Buffer distance must be in (0, {MAX_BUFFER_KM:g}] km.")
    centre = geometry.centroid
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={centre.y} +lon_0={centre.x} +datum=WGS84 +units=m +no_defs"
    )
    forward = Transformer.from_crs("EPSG:4326", local, always_xy=True).transform
    inverse = Transformer.from_crs(local, "EPSG:4326", always_xy=True).transform
    return transform(inverse, transform(forward, geometry).buffer(distance_km * 1000.0, 32))


###############################################################################
def check_bounds(geometries: list[BaseGeometry | None]) -> None:
    """Keep geometry work inside the bounded tool contract."""

    if len(geometries) > MAX_GEOMETRY_RECORDS:
        raise GeometryOperationError(
            f"Geometry operations accept at most {MAX_GEOMETRY_RECORDS} records; filter or limit first."
        )
    vertices = sum(_vertex_count(item) for item in geometries if item is not None)
    if vertices > MAX_TOTAL_VERTICES:
        raise GeometryOperationError(
            f"Geometries carry {vertices} vertices (limit {MAX_TOTAL_VERTICES}); use a coarser boundary level."
        )


###############################################################################
def spatial_join(
    targets: list[dict[str, Any]],
    joins: list[dict[str, Any]],
    *,
    predicate: str,
    mode: str,
    distance_km: float | None,
    properties: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Relate each target to the join records that match the predicate.

    ``within``: the join geometry lies within the target; ``intersects``: they
    share any point; ``within_distance``: the join geometry is within
    ``distance_km`` of the target (the target is buffered by that distance).
    ``count`` adds ``joined_count``; ``attach`` also copies the scalar fields
    of the first matching join record as ``join_<field>``; ``filter`` keeps only
    matched targets.
    """

    target_shapes = [record_geometry(item) for item in targets]
    join_shapes = [record_geometry(item) for item in joins]
    check_bounds([*target_shapes, *join_shapes])
    indexed = [(index, geom) for index, geom in enumerate(join_shapes) if geom is not None]
    if not indexed:
        raise GeometryOperationError("The join evidence has no located records.")
    tree = STRtree([geom for _index, geom in indexed])
    output: list[dict[str, Any]] = []
    for item, geometry in zip(targets, target_shapes, strict=True):
        if geometry is None:
            continue
        area = buffer_km(geometry, float(distance_km or 0)) if predicate == "within_distance" else geometry
        candidates = tree.query(area)
        matched: list[int] = []
        for position in candidates:
            join_index, join_geometry = indexed[int(position)]
            if (
                area.covers(join_geometry) if predicate == "within" else area.intersects(join_geometry)
            ):
                matched.append(join_index)
        if mode == "filter" and not matched:
            continue
        properties(item)["joined_count"] = len(matched)
        if mode == "attach" and matched:
            first = properties(joins[min(matched)])
            scalars = [
                (key, value) for key, value in first.items()
                if not isinstance(value, dict | list) and key not in {"source_ref", "source_place"}
            ]
            for key, value in scalars[:MAX_ATTACHED_FIELDS]:
                properties(item)[f"join_{key}"] = value
        output.append(item)
    return output


###############################################################################
def overlay(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    kind: str,
    properties: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Polygon overlay between two evidence sets.

    ``intersection``: each overlapping left/right pair; ``difference``: each
    left geometry minus the right union; ``clip``: left records (any geometry)
    cut to the right union; ``union``: one dissolved geometry of both sides.
    The right side must be polygonal; intersection, difference and union also
    need polygonal left geometries. Point footprints are refused rather than
    treated as areas.
    """

    left_shapes = [record_geometry(item) for item in left]
    right_shapes = [record_geometry(item) for item in right]
    check_bounds([*left_shapes, *right_shapes])
    right_polygons = [geom for geom in right_shapes if is_polygonal(geom)]
    if not right_polygons:
        raise GeometryOperationError(
            "The second evidence set has no polygon footprints; point or bbox-only "
            "locations cannot be overlaid as areas."
        )
    if kind != "clip" and not any(is_polygonal(geom) for geom in left_shapes):
        raise GeometryOperationError(
            f"{kind} needs polygon footprints in the first evidence set; use clip for points."
        )
    if kind == "union":
        dissolved = unary_union([geom for geom in left_shapes if is_polygonal(geom)] + right_polygons)
        return [_area_record({"properties": {"overlay": "union"}}, dissolved, properties)]
    if kind == "intersection":
        tree = STRtree(right_polygons)
        output: list[dict[str, Any]] = []
        for item, geometry in zip(left, left_shapes, strict=True):
            if not is_polygonal(geometry):
                continue
            for position in tree.query(geometry):
                piece = geometry.intersection(right_polygons[int(position)])
                if not piece.is_empty and is_polygonal(piece):
                    output.append(_area_record(_copy(item), piece, properties))
        return output
    mask = unary_union(right_polygons)
    output = []
    for item, geometry in zip(left, left_shapes, strict=True):
        if geometry is None or (kind == "difference" and not is_polygonal(geometry)):
            continue
        piece = geometry.difference(mask) if kind == "difference" else geometry.intersection(mask)
        if piece.is_empty:
            continue
        record = _copy(item)
        if is_polygonal(piece):
            output.append(_area_record(record, piece, properties))
        else:
            record["geometry"] = mapping(piece)
            output.append(record)
    return output


###############################################################################
def with_area(
    item: dict[str, Any], properties: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    """Add geodesic area_km2 and perimeter_km to a polygonal record."""

    geometry = record_geometry(item)
    if is_polygonal(geometry):
        area, perimeter = geodesic_area_perimeter_km(geometry)
        properties(item)["area_km2"] = round(area, 3)
        properties(item)["perimeter_km"] = round(perimeter, 3)
    return item


###############################################################################
def _area_record(
    item: dict[str, Any],
    geometry: BaseGeometry,
    properties: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    item["geometry"] = mapping(geometry)
    item.setdefault("type", "Feature")
    return with_area(item, properties)


###############################################################################
def _copy(item: dict[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    if is_json_object(item.get("properties")):
        copied["properties"] = dict(item["properties"])
    return copied


###############################################################################
def _vertex_count(geometry: BaseGeometry) -> int:
    return int(cast(int, shapely.get_num_coordinates(geometry)))  # pyright: ignore[reportUnknownMemberType]
