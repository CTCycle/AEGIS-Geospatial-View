from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.services.geospatial.map_session_builder import _viewport_for_location


###############################################################################
def test_city_with_parent_scale_bbox_keeps_point_centered_viewport() -> None:
    location = ResolvedLocation(
        label="Tokyo, Japan",
        latitude=35.6768601,
        longitude=139.7638947,
        location_type="city",
        bbox=[135.8536855, 20.2145811, 154.205541, 35.8984245],
    )

    viewport = _viewport_for_location(location)

    assert viewport.center_latitude == location.latitude
    assert viewport.center_longitude == location.longitude
    assert viewport.bbox is None


###############################################################################
def test_point_like_feature_bbox_keeps_a_usable_context_viewport() -> None:
    location = ResolvedLocation(
        label="Great Barrier Reef, Australia",
        latitude=-16.35,
        longitude=145.9,
        location_type="reef",
        bbox=[145.89995, -16.35005, 145.90005, -16.34995],
    )

    viewport = _viewport_for_location(location)

    assert viewport.center_latitude == location.latitude
    assert viewport.center_longitude == location.longitude
    assert viewport.bbox is None
