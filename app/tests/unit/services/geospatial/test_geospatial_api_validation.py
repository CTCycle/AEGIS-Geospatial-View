from __future__ import annotations

import math

import pytest

from server.services.geospatial.api_service import (
    GeospatialApiService,
    GeospatialInvalidRequestError,
    GeospatialProviderResponseError,
    normalize_geojson_feature_collection,
)


###############################################################################
def test_geojson_normalization_preserves_valid_geometry_and_coordinates() -> None:
    result = normalize_geojson_feature_collection(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "point-1",
                    "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
                    "properties": {"name": "valid"},
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[12.4, 41.8], [12.6, 41.8], [12.6, 42.0], [12.4, 41.8]]
                        ],
                    },
                    "properties": {},
                },
            ],
        }
    )

    assert len(result["features"]) == 2
    assert result["features"][0]["geometry"]["coordinates"] == [12.5, 41.9]


###############################################################################
@pytest.mark.parametrize(
    "payload",
    [
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [181, 41]},
                    "properties": {},
                }
            ],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {},
                }
            ],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [12, math.nan]},
                    "properties": {},
                }
            ],
        },
    ],
)
def test_geojson_normalization_rejects_invalid_geometry(payload: dict) -> None:
    with pytest.raises(GeospatialProviderResponseError, match="invalid geometry"):
        normalize_geojson_feature_collection(payload)


###############################################################################
def test_geojson_normalization_converts_latitude_longitude_records() -> None:
    result = normalize_geojson_feature_collection(
        {
            "features": [
                {
                    "id": "station-1",
                    "latitude": 41.9,
                    "longitude": 12.5,
                    "value": 4.2,
                }
            ]
        }
    )

    feature = result["features"][0]
    assert feature["geometry"] == {
        "type": "Point",
        "coordinates": [12.5, 41.9],
    }
    assert feature["properties"]["value"] == 4.2


###############################################################################
def test_bbox_parser_enforces_west_south_east_north_and_finite_values() -> None:
    service = object.__new__(GeospatialApiService)

    assert service._parse_bbox("12.0,41.0,13.0,42.0") == (
        12.0,
        41.0,
        13.0,
        42.0,
    )
    with pytest.raises(GeospatialInvalidRequestError, match="ordered"):
        service._parse_bbox("13.0,41.0,12.0,42.0")
    with pytest.raises(GeospatialInvalidRequestError, match="finite"):
        service._parse_bbox("12.0,41.0,nan,42.0")
