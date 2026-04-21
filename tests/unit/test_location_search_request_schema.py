from __future__ import annotations

import pytest
from pydantic import ValidationError

from AEGIS.server.domain.geographics import LocationSearchRequest


def _base_payload() -> dict[str, object]:
    return {
        "datetime": "2024-06-15T12:00:00",
        "use_coordinates": True,
        "latitude": 41.9,
        "longitude": 12.5,
    }


def test_accepts_canonical_request_fields() -> None:
    request = LocationSearchRequest.model_validate(
        {
            **_base_payload(),
            "basemap_id": "osm_default",
            "overlay_ids": ["openaq_air_quality"],
            "semantic_filters": ["air_quality"],
        }
    )
    assert request.basemap_id == "osm_default"
    assert request.overlay_ids == ["openaq_air_quality"]
    assert request.semantic_filters == ["air_quality"]


@pytest.mark.parametrize(
    "legacy_field,value",
    [
        ("map_tiles", "OpenStreetMap"),
        ("geospatial_filter", ["air_quality"]),
        ("geospatial_layers", ["air_quality"]),
    ],
)
def test_rejects_removed_legacy_fields(legacy_field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        LocationSearchRequest.model_validate({**_base_payload(), legacy_field: value})
