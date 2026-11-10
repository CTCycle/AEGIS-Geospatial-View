from __future__ import annotations

import math

import pytest

from server.services.geospatial import geometry_ops
from server.services.geospatial.geometry_ops import GeometryOperationError
from server.services.agent.tool_handlers.evidence import _apply_operations, _properties


def square(name: str, west: float, south: float, size: float, ref: str = "regions") -> dict[str, object]:
    ring = [[west, south], [west + size, south], [west + size, south + size], [west, south + size], [west, south]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"name": name, "source_ref": ref}}


def point(lon: float, lat: float, ref: str = "quakes", **values: object) -> dict[str, object]:
    return {"longitude": lon, "latitude": lat, "source_ref": ref, **values}


###############################################################################
def test_geodesic_area_and_true_distance_buffer() -> None:
    # One degree square at the equator is about 12,309 km².
    [record], error = _apply_operations([square("eq", 0, 0, 1)], [{"op": "area"}])
    assert error is None and _properties(record)["area_km2"] == pytest.approx(12_309, rel=0.01)

    [buffered], error = _apply_operations([point(10, 60)], [{"op": "buffer", "distance_km": 10}])
    assert error is None and buffered["buffer_km"] == 10
    # A 10 km radius is πr² regardless of latitude.
    assert buffered["area_km2"] == pytest.approx(math.pi * 100, rel=0.01)


###############################################################################
def test_spatial_join_counts_attaches_and_filters_by_distance() -> None:
    records = [square("north", 0, 1, 1), square("south", 0, 0, 1),
               point(0.5, 1.5, magnitude=4.1), point(0.4, 1.6, magnitude=3.0), point(5, 5, magnitude=2.0)]
    join = {"op": "spatial_join", "target_ref": "regions", "join_ref": "quakes"}
    counted, error = _apply_operations([dict(item) for item in records], [join])
    assert error is None
    assert {_properties(item)["name"]: _properties(item)["joined_count"] for item in counted} == {"north": 2, "south": 0}

    attached, _ = _apply_operations(records, [{**join, "mode": "attach"}])
    north = next(item for item in attached if _properties(item)["name"] == "north")
    assert _properties(north)["join_magnitude"] == 4.1

    near = [point(0, 0, ref="schools", name="near"), point(1, 1, ref="schools", name="far"),
            square("flood", 0.01, -0.5, 0.5, ref="flood")]
    kept, error = _apply_operations(near, [{"op": "spatial_join", "target_ref": "schools", "join_ref": "flood",
                                             "predicate": "within_distance", "distance_km": 2, "mode": "filter"}])
    assert error is None and [item["name"] for item in kept] == ["near"]


###############################################################################
def test_overlay_refuses_point_footprints_and_clips_points() -> None:
    zones = [square("zone", 0, 0, 1, ref="zones")]
    events = [point(0.5, 0.5, ref="events"), point(3, 3, ref="events")]
    _, error = _apply_operations(events + zones, [{"op": "overlay", "left_ref": "zones", "right_ref": "events"}])
    assert error is not None and "polygon footprints" in error

    clipped, error = _apply_operations(events + zones, [{"op": "overlay", "left_ref": "events",
                                                         "right_ref": "zones", "kind": "clip"}])
    assert error is None and len(clipped) == 1

    halves = [square("a", 0, 0, 1, ref="left"), square("b", 0.5, 0, 1, ref="right")]
    [piece], error = _apply_operations(halves, [{"op": "overlay", "left_ref": "left", "right_ref": "right"}])
    assert error is None and _properties(piece)["area_km2"] == pytest.approx(12_309 / 2, rel=0.01)


###############################################################################
def test_geometry_operations_are_bounded() -> None:
    too_many = [point(0, 0) for _ in range(geometry_ops.MAX_GEOMETRY_RECORDS + 1)]
    _, error = _apply_operations(too_many, [{"op": "buffer", "distance_km": 1}])
    assert error is not None and "at most" in error
    with pytest.raises(GeometryOperationError):
        geometry_ops.buffer_km(geometry_ops.record_geometry(point(0, 0)), 501)  # type: ignore[arg-type]
