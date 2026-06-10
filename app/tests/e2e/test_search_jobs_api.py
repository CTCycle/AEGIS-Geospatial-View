from __future__ import annotations

import time

from playwright.sync_api import APIRequestContext


###############################################################################
def _payload() -> dict[str, object]:
    return {
        "resolved_location": {
            "label": "Rome, Italy",
            "latitude": 41.9028,
            "longitude": 12.4964,
            "country": "Italy",
            "city": "Rome",
            "source": "test",
            "confidence": 1.0,
        },
        "action_id": "map_search",
        "time_mode": "current",
        "basemap_id": "osm_default",
        "overlay_ids": [],
        "viewport": {
            "center_latitude": 41.9028,
            "center_longitude": 12.4964,
            "radius_m": 2500.0,
            "bbox": [12.3, 41.8, 12.7, 42.0],
        },
        "presentation": {
            "emphasize_overlays": False,
            "high_contrast": False,
            "show_legend": True,
        },
    }


###############################################################################
def test_start_poll_cancel_and_idempotence(api_context: APIRequestContext) -> None:
    start = api_context.post("/api/maps/jobs", data=_payload())
    assert start.status in {202, 502, 503, 504}
    if start.status != 202:
        return
    job_id = start.json()["job_id"]

    latest = None
    for _ in range(30):
        status_resp = api_context.get(f"/api/maps/jobs/{job_id}")
        assert status_resp.ok
        latest = status_resp.json()
        if latest["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    assert latest is not None
    assert latest["job_id"] == job_id

    cancel_resp = api_context.delete(f"/api/maps/jobs/{job_id}")
    assert cancel_resp.ok
    cancel_again = api_context.delete(f"/api/maps/jobs/{job_id}")
    assert cancel_again.ok


###############################################################################
def test_unknown_job_id_behavior(api_context: APIRequestContext) -> None:
    status_missing = api_context.get("/api/maps/jobs/unknown-job-id")
    cancel_missing = api_context.delete("/api/maps/jobs/unknown-job-id")
    assert status_missing.status == 404
    assert cancel_missing.status == 404


###############################################################################
def test_memory_backed_non_durable_semantics_shape(
    api_context: APIRequestContext,
) -> None:
    start = api_context.post("/api/maps/jobs", data=_payload())
    assert start.status in {202, 502, 503, 504}
    if start.status != 202:
        return
    body = start.json()
    assert body["job_type"] == "map_fetch"
    assert "poll_interval" in body
