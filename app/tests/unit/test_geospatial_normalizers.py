from __future__ import annotations

import pytest

from server.services.geospatial.normalizers import (
    NormalizationError,
    deduplicate_poi_features,
    normalize_camera_feature,
    normalize_poi_category,
    normalize_poi_feature,
)


###############################################################################
def test_normalize_poi_feature_accepts_common_coordinate_aliases() -> None:
    poi = normalize_poi_feature(
        {
            "id": "osm-1",
            "name": "Water point",
            "lat": "45.1",
            "lon": "7.2",
            "website": "https://example.test",
            "raw_tag": "drinking_water",
        },
        source="overpass",
        category="drinking_water",
    )

    assert poi.id == "osm-1"
    assert poi.latitude == 45.1
    assert poi.longitude == 7.2
    assert poi.metadata == {"raw_tag": "drinking_water"}


###############################################################################
def test_normalize_camera_feature_requires_official_url() -> None:
    with pytest.raises(NormalizationError):
        normalize_camera_feature(
            {"id": "cam-1", "latitude": 45.1, "longitude": 7.2},
            provider="windy_webcams",
            camera_type="webcam",
        )


###############################################################################
def test_normalize_camera_feature_defaults_to_no_embedding() -> None:
    camera = normalize_camera_feature(
        {
            "id": "cam-1",
            "name": "Pass camera",
            "latitude": 45.1,
            "longitude": 7.2,
            "official_url": "https://example.test/cam",
            "preview_image_url": "https://example.test/preview.jpg",
        },
        provider="windy_webcams",
        camera_type="webcam",
    )

    assert camera.embedding_allowed is False
    assert camera.embed_url is None
    assert camera.official_url == "https://example.test/cam"


###############################################################################
def test_normalize_poi_category_maps_phase8_sources() -> None:
    assert normalize_poi_category("charging station") == "ev_charging"
    assert normalize_poi_category("gas-station") == "fuel"
    assert normalize_poi_category("railway") == "rail"
    assert normalize_poi_category("pipeline") == "pipelines"
    assert normalize_poi_category("museum") == "tourism"
    assert normalize_poi_category("heliport") == "airports"
    assert normalize_poi_category("fuel stations") == "fuel"
    assert normalize_poi_category("power substation") == "power"
    assert normalize_poi_category("communication tower") == "telecom"
    assert normalize_poi_category("hiking trail") == "trails"
    assert normalize_poi_category("marina") == "ports"
    assert normalize_poi_category("railway station") == "rail"


###############################################################################
def test_deduplicate_poi_features_by_name_category_and_coordinates() -> None:
    first = normalize_poi_feature(
        {"id": "osm-1", "name": "Central Charger", "lat": 45.0, "lon": 7.0},
        source="overpass",
        category="charging_station",
    )
    duplicate = normalize_poi_feature(
        {"id": "ocm-1", "name": "Central Charger", "lat": 45.000004, "lon": 7.000004},
        source="openchargemap",
        category="ev_charging",
    )
    different = normalize_poi_feature(
        {"id": "nrel-1", "name": "Central Fuel", "lat": 45.0, "lon": 7.0},
        source="nrel",
        category="fuel",
    )

    deduplicated = deduplicate_poi_features([first, duplicate, different])

    assert [feature.id for feature in deduplicated] == ["osm-1", "nrel-1"]
