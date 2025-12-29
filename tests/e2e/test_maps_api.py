"""
E2E tests for Maps search API endpoints.
Tests: POST /maps/search validation, overlays, and session recording.
"""
import pytest
from playwright.sync_api import APIRequestContext


DEFAULT_COORDINATES = {"latitude": 41.9028, "longitude": 12.4964}


def build_coordinate_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "datetime": "2024-06-15T12:00:00",
        "use_coordinates": True,
        **DEFAULT_COORDINATES,
    }
    payload.update(overrides)
    return payload


def post_search(api_context: APIRequestContext, payload: dict[str, object]):
    return api_context.post("/maps/search", json=payload)


def assert_error_contains(response, expected: str) -> None:
    body = response.json()
    detail = body.get("detail", body)
    messages: list[str] = []
    if isinstance(detail, list):
        for item in detail:
            if isinstance(item, dict):
                messages.append(str(item.get("msg") or item.get("detail") or item))
            else:
                messages.append(str(item))
    else:
        messages.append(str(detail))
    assert expected.lower() in " ".join(messages).lower()


class TestMapSearchSuccess:
    """Happy path tests for map search."""

    def test_search_by_coordinates_returns_satellite_payload(self, api_context: APIRequestContext):
        response = post_search(api_context, build_coordinate_payload())
        assert response.ok, f"Expected 200, got {response.status}"

        data = response.json()
        assert data.get("status_message") == "Map search request submitted."
        payload = data.get("payload", {})
        payload_lat = payload.get("latitude")
        payload_lon = payload.get("longitude")
        assert isinstance(payload_lat, (int, float))
        assert isinstance(payload_lon, (int, float))
        assert abs(payload_lat - DEFAULT_COORDINATES["latitude"]) < 0.001
        assert abs(payload_lon - DEFAULT_COORDINATES["longitude"]) < 0.001
        imagery = payload.get("satellite_imagery", {})
        assert isinstance(imagery.get("map_html"), str)
        assert imagery.get("map_html"), "Expected map HTML to be populated."

    def test_search_with_openaq_overlay_includes_overlays(self, api_context: APIRequestContext):
        payload = build_coordinate_payload(geospatial_layers=["OpenAQ_Air_Quality"])
        response = post_search(api_context, payload)
        assert response.ok, f"Expected 200, got {response.status}"

        data = response.json()
        overlays = data.get("payload", {}).get("satellite_imagery", {}).get("overlays", [])
        assert isinstance(overlays, list)
        assert overlays, "Expected at least one overlay entry."
        assert any(entry.get("provider") == "openaq" for entry in overlays)

    def test_search_with_gibs_overlay_includes_overlays(self, api_context: APIRequestContext):
        payload = build_coordinate_payload(
            geospatial_layers=["VIIRS_SNPP_CorrectedReflectance_TrueColor"],
            image_width=512,
            image_height=512,
        )
        response = post_search(api_context, payload)
        if response.status == 502:
            pytest.skip("GIBS service unavailable for overlay fetch.")
        assert response.ok, f"Expected 200, got {response.status}"

        data = response.json()
        overlays = data.get("payload", {}).get("satellite_imagery", {}).get("overlays", [])
        assert isinstance(overlays, list)
        assert overlays, "Expected at least one overlay entry."
        assert any(entry.get("provider") == "gibs" for entry in overlays)

    def test_search_records_session(self, api_context: APIRequestContext):
        before = api_context.get("/browser/tables/SEARCH_SESSIONS/stats").json()
        before_count = int(before.get("rowCount", 0))

        response = post_search(api_context, build_coordinate_payload())
        assert response.ok, f"Expected 200, got {response.status}"

        after = api_context.get("/browser/tables/SEARCH_SESSIONS/stats").json()
        after_count = int(after.get("rowCount", 0))
        assert after_count >= before_count + 1


class TestMapSearchValidation:
    """Validation error handling for map search."""

    def test_search_missing_datetime_returns_422(self, api_context: APIRequestContext):
        payload = build_coordinate_payload()
        payload.pop("datetime", None)
        response = post_search(api_context, payload)
        assert response.status == 422
        assert_error_contains(response, "Provide datetime")

    def test_search_requires_coordinates_when_enabled(self, api_context: APIRequestContext):
        payload = build_coordinate_payload()
        payload.pop("latitude", None)
        response = post_search(api_context, payload)
        assert response.status == 422
        assert_error_contains(response, "Provide both latitude and longitude")

    def test_search_invalid_bbox_returns_422(self, api_context: APIRequestContext):
        payload = build_coordinate_payload(bbox=[10, 10, 5, 12])
        response = post_search(api_context, payload)
        assert response.status == 422
        assert_error_contains(response, "BBox min values must be smaller than max values")

    def test_search_invalid_crs_returns_400(self, api_context: APIRequestContext):
        payload = build_coordinate_payload(image_crs="EPSG:9999")
        response = post_search(api_context, payload)
        assert response.status == 400
        assert_error_contains(response, "Unsupported target CRS")
