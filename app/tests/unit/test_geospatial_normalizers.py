from __future__ import annotations

import pytest

from server.services.geospatial.normalizers import (
    NormalizationError,
    normalize_camera_feature,
    normalize_poi_feature,
)


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


def test_normalize_camera_feature_requires_official_url() -> None:
    with pytest.raises(NormalizationError):
        normalize_camera_feature(
            {"id": "cam-1", "latitude": 45.1, "longitude": 7.2},
            provider="windy_webcams",
            camera_type="webcam",
        )


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
