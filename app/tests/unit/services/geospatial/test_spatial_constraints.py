from __future__ import annotations

import pytest

from server.services.geospatial.spatial_constraints import (
    SpatialConstraintError,
    feature_matches_constraint,
    geodesic_distance_m,
    normalize_bbox,
    validate_geojson_geometry,
    validate_point,
)

###############################################################################
def test_bbox_uses_west_south_east_north_and_preserves_antimeridian_wrap() -> None:
    assert normalize_bbox([8.0, 45.0, 9.0, 46.0]) == [8.0, 45.0, 9.0, 46.0]
    assert normalize_bbox([170.0, -10.0, -170.0, 10.0]) == [170.0, -10.0, -170.0, 10.0]

    with pytest.raises(SpatialConstraintError, match="equal longitudes"):
        normalize_bbox([8.0, 45.0, 8.0, 46.0])

###############################################################################
def test_invalid_coordinates_and_geometry_fail_closed() -> None:
    with pytest.raises(SpatialConstraintError):
        validate_point(91.0, 0.0)
    with pytest.raises(SpatialConstraintError):
        validate_point(True, 0.0)
    with pytest.raises(SpatialConstraintError):
        validate_point(float("nan"), 0.0)
    with pytest.raises(SpatialConstraintError):
        validate_geojson_geometry({"type": "Polygon", "coordinates": []})

###############################################################################
def test_radius_uses_wgs84_geodesic_distance() -> None:
    distance = geodesic_distance_m(0.0, 0.0, 0.0, 1.0)
    assert 110_000 < distance < 112_000

###############################################################################
def test_containment_and_distance_are_applied_to_feature_geometry() -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [[[8.0, 45.0], [9.0, 45.0], [9.0, 46.0], [8.0, 46.0], [8.0, 45.0]]],
    }
    inside = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [8.5, 45.5]}}
    outside = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.0, 45.5]}}

    assert feature_matches_constraint(
        inside,
        relationship="in",
        reference_geometry=polygon,
    ) is True
    assert feature_matches_constraint(
        outside,
        relationship="in",
        reference_geometry=polygon,
    ) is False
    assert feature_matches_constraint(
        inside,
        relationship="within_distance",
        reference_point=(45.5, 8.5),
        distance_m=10,
    ) is True
    assert feature_matches_constraint(
        outside,
        relationship="within_distance",
        reference_point=(45.5, 8.5),
        distance_m=10,
    ) is False

###############################################################################
def test_distance_uses_the_nearest_part_of_nonpoint_geometry() -> None:
    line = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[8.5001, 45.5], [12.0, 50.0]],
        },
    }

    assert feature_matches_constraint(
        line,
        relationship="within_distance",
        reference_point=(45.5, 8.5),
        distance_m=20,
    ) is True
