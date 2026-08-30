from __future__ import annotations

from server.services.geospatial.inspection import MapInspectionService


###############################################################################
def test_feature_metadata_is_bounded_and_allowlisted() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "weather-points",
            "label": "Weather stations",
            "provider": "official-feed",
            "rendering_mode": "geojson",
            "data": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "id": "station-1",
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [8.54, 47.37]},
                        "properties": {
                            "name": "Zurich",
                            "metric": "temperature",
                            "value": 21.5,
                            "unit": "C",
                            "secret": {"not": "a scalar"},
                            "long_note": "x" * 500,
                        },
                    }
                ],
            },
        }
    )

    assert len(inspections) == 1
    inspection = inspections[0]
    assert inspection.association == "feature"
    assert inspection.feature_id == "station-1"
    assert {field.key for field in inspection.fields} == {
        "name",
        "metric",
        "value",
        "unit",
    }
    assert all(
        len(str(field.value)) <= MapInspectionService.MAX_TEXT
        for field in inspection.fields
    )


###############################################################################
def test_location_metadata_gets_point_association() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "camera-1",
            "label": "Camera 1",
            "provider": "traffic-feed",
            "inspection_metadata": {
                "name": "Zurich camera",
                "status": "online",
                "latitude": 47.3769,
                "longitude": 8.5417,
                "official_url": "https://example.test/camera/1",
            },
        }
    )

    assert len(inspections) == 1
    inspection = inspections[0]
    assert inspection.association == "location"
    assert inspection.geometry == {"type": "Point", "coordinates": [8.5417, 47.3769]}
    assert inspection.source_url == "https://example.test/camera/1"


###############################################################################
def test_raster_metadata_is_overlay_level_and_rejects_unsafe_links() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "rain-radar",
            "label": "Rain radar",
            "provider": "weather-feed",
            "rendering_mode": "raster-tile",
            "time": "2026-08-27T10:00:00Z",
            "units": "mm/h",
            "freshness": "updated 5 minutes ago",
            "source_url": "javascript:alert(1)",
            "warnings": ["Values are not available per raster cell."],
            "stale": True,
        }
    )

    assert len(inspections) == 1
    inspection = inspections[0]
    assert inspection.association == "overlay"
    assert inspection.stale is True
    assert inspection.source_url is None
    assert any(field.key == "units" for field in inspection.fields)
    assert inspection.warnings == ["Values are not available per raster cell."]


###############################################################################
def test_non_spatial_dataset_metadata_remains_inspectable() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "population",
            "label": "Population dataset",
            "provider": "statistics",
            "metadata": {
                "metric": "population",
                "period": "2025",
                "geography": "Switzerland",
                "source": "Federal Statistical Office",
                "license": "CC BY",
                "update_time": "2026-01-01",
            },
        }
    )

    assert len(inspections) == 1
    assert inspections[0].association == "non_spatial"
    assert {field.key for field in inspections[0].fields} == {
        "metric",
        "period",
        "geography",
        "source",
        "license",
        "update_time",
    }
