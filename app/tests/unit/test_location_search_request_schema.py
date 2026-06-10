from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.domain.geographics import LocationSearchRequest


###############################################################################
def _base_payload() -> dict[str, object]:
    return {
        "resolved_location": {
            "label": "Rome, Italy",
            "latitude": 41.9,
            "longitude": 12.5,
            "city": "Rome",
            "country": "Italy",
        },
        "action_id": "air_quality",
        "time_mode": "current",
        "viewport": {
            "center_latitude": 41.9,
            "center_longitude": 12.5,
            "radius_m": 2500.0,
        },
    }


###############################################################################
def test_accepts_canonical_request_fields() -> None:
    request = LocationSearchRequest.model_validate(
        {
            **_base_payload(),
            "basemap_id": "osm_default",
            "overlay_ids": ["openaq_air_quality"],
            "presentation": {
                "emphasize_overlays": True,
                "high_contrast": False,
                "show_legend": True,
            },
        }
    )
    assert request.basemap_id == "osm_default"
    assert request.overlay_ids == ["openaq_air_quality"]
    assert request.resolved_location.city == "Rome"


###############################################################################
@pytest.mark.parametrize(
    "removed_field,value",
    [
        ("map_tiles", "OpenStreetMap"),
        ("geospatial_filter", ["air_quality"]),
        ("geospatial_layers", ["air_quality"]),
    ],
)
def test_rejects_removed_request_fields(removed_field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        LocationSearchRequest.model_validate({**_base_payload(), removed_field: value})
