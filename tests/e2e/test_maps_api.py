from __future__ import annotations

import time

import pytest
from playwright.sync_api import APIRequestContext


DEFAULT_COORDINATES = {"latitude": 41.9028, "longitude": 12.4964}


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "datetime": "2024-06-15T12:00:00",
        "use_coordinates": True,
        **DEFAULT_COORDINATES,
    }
    base.update(overrides)
    return base


def _post(api_context: APIRequestContext, path: str, payload: dict[str, object]):
    return api_context.post(path, data=payload)


def _get(api_context: APIRequestContext, path: str):
    return api_context.get(path)


def _delete(api_context: APIRequestContext, path: str):
    return api_context.delete(path)


def _assert_degraded_or_ok(response) -> None:  # noqa: ANN001
    if response.status in {502, 503, 504}:
        detail = str(response.json().get("detail", ""))
        assert detail
        pytest.skip(f"External provider degraded: {response.status}")


def test_search_coordinates_and_prefix_parity(api_context: APIRequestContext) -> None:
    base = _post(api_context, "/maps/search", _payload())
    prefixed = _post(api_context, "/api/maps/search", _payload())
    _assert_degraded_or_ok(base)
    _assert_degraded_or_ok(prefixed)
    assert base.ok and prefixed.ok
    base_body = base.json()
    prefixed_body = prefixed.json()
    assert base_body.get("status_message") == "Map search request submitted."
    assert set(base_body.keys()) == set(prefixed_body.keys())


def test_catalog_success_and_prefix_parity(api_context: APIRequestContext) -> None:
    base = _get(api_context, "/maps/catalog")
    prefixed = _get(api_context, "/api/maps/catalog")
    assert base.ok and prefixed.ok
    body = base.json()
    assert isinstance(body.get("providers"), list)
    assert isinstance(body.get("basemaps"), list)
    assert isinstance(body.get("overlays"), list)
    assert set(body.keys()) == set(prefixed.json().keys())


def test_osm_basemap_tile_proxy_returns_png_and_prefix_parity(api_context: APIRequestContext) -> None:
    base = _get(api_context, "/maps/basemaps/osm/13/4380/3043.png")
    prefixed = _get(api_context, "/api/maps/basemaps/osm/13/4380/3043.png")
    if base.status in {502, 503, 504} or prefixed.status in {502, 503, 504}:
        pytest.skip("OSM tile provider unavailable during test run")
    assert base.ok and prefixed.ok
    assert base.headers["content-type"].startswith("image/png")
    assert prefixed.headers["content-type"].startswith("image/png")
    assert int(base.headers.get("content-length", "1")) > 0
    assert int(prefixed.headers.get("content-length", "1")) > 0


def test_malformed_search_payload_returns_422(api_context: APIRequestContext) -> None:
    response = _post(api_context, "/maps/search", _payload(latitude=None))
    assert response.status == 422


def test_jobs_start_status_cancel_and_idempotence(api_context: APIRequestContext) -> None:
    start = _post(api_context, "/maps/jobs", _payload())
    _assert_degraded_or_ok(start)
    assert start.status == 202
    body = start.json()
    job_id = body["job_id"]

    status_response = _get(api_context, f"/maps/jobs/{job_id}")
    assert status_response.ok
    assert status_response.json()["job_id"] == job_id

    cancel_response = _delete(api_context, f"/maps/jobs/{job_id}")
    assert cancel_response.ok
    cancel_body = cancel_response.json()
    assert cancel_body["job_id"] == job_id
    assert isinstance(cancel_body["success"], bool)

    cancel_again = _delete(api_context, f"/maps/jobs/{job_id}")
    assert cancel_again.ok
    assert cancel_again.json()["job_id"] == job_id


def test_jobs_prefix_parity_and_unknown_job(api_context: APIRequestContext) -> None:
    start_base = _post(api_context, "/maps/jobs", _payload())
    _assert_degraded_or_ok(start_base)
    assert start_base.status == 202
    job_id = start_base.json()["job_id"]

    start_prefixed = _post(api_context, "/api/maps/jobs", _payload())
    _assert_degraded_or_ok(start_prefixed)
    assert start_prefixed.status == 202

    status_base = _get(api_context, f"/maps/jobs/{job_id}")
    status_prefixed = _get(api_context, f"/api/maps/jobs/{job_id}")
    assert status_base.ok and status_prefixed.ok
    assert set(status_base.json().keys()) == set(status_prefixed.json().keys())

    missing = _get(api_context, "/maps/jobs/does-not-exist")
    assert missing.status == 404


def test_search_graceful_behavior_when_provider_degrades(api_context: APIRequestContext) -> None:
    response = _post(api_context, "/maps/search", _payload(geospatial_layers=["VIIRS_SNPP_CorrectedReflectance_TrueColor"]))
    if response.ok:
        assert "status_message" in response.json()
        return
    assert response.status in {400, 502, 503, 504}
    detail = str(response.json().get("detail", ""))
    assert detail


def test_search_with_overlay_ids_includes_overlays(api_context: APIRequestContext) -> None:
    response = _post(
        api_context,
        "/maps/search",
        _payload(
            overlay_ids=["openaq_air_quality", "pvgis_solar"],
            basemap_id="osm_default",
        ),
    )
    _assert_degraded_or_ok(response)
    assert response.ok
    overlays = response.json().get("payload", {}).get("map_session", {}).get("overlays", [])
    assert isinstance(overlays, list)


def test_job_status_poll_until_terminal_or_timeout(api_context: APIRequestContext) -> None:
    start = _post(api_context, "/maps/jobs", _payload())
    _assert_degraded_or_ok(start)
    assert start.status == 202
    job_id = start.json()["job_id"]

    terminal = {"completed", "failed", "cancelled"}
    latest = None
    for _ in range(30):
        status_resp = _get(api_context, f"/maps/jobs/{job_id}")
        assert status_resp.ok
        latest = status_resp.json()
        if latest["status"] in terminal:
            break
        time.sleep(0.1)
    assert latest is not None
    assert latest["job_id"] == job_id
