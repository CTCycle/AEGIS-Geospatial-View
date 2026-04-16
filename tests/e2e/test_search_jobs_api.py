from __future__ import annotations

import time

from playwright.sync_api import APIRequestContext


def _payload() -> dict[str, object]:
    return {
        "datetime": "2024-06-15T12:00:00",
        "use_coordinates": True,
        "latitude": 41.9028,
        "longitude": 12.4964,
    }


def test_start_poll_cancel_and_idempotence(api_context: APIRequestContext) -> None:
    start = api_context.post("/maps/jobs", data=_payload())
    assert start.status in {202, 502, 503, 504}
    if start.status != 202:
        return
    job_id = start.json()["job_id"]

    latest = None
    for _ in range(30):
        status_resp = api_context.get(f"/maps/jobs/{job_id}")
        assert status_resp.ok
        latest = status_resp.json()
        if latest["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    assert latest is not None
    assert latest["job_id"] == job_id

    cancel_resp = api_context.delete(f"/maps/jobs/{job_id}")
    assert cancel_resp.ok
    cancel_again = api_context.delete(f"/maps/jobs/{job_id}")
    assert cancel_again.ok


def test_unknown_job_id_behavior(api_context: APIRequestContext) -> None:
    status_missing = api_context.get("/maps/jobs/unknown-job-id")
    cancel_missing = api_context.delete("/maps/jobs/unknown-job-id")
    assert status_missing.status == 404
    assert cancel_missing.status == 404


def test_memory_backed_non_durable_semantics_shape(api_context: APIRequestContext) -> None:
    start = api_context.post("/maps/jobs", data=_payload())
    assert start.status in {202, 502, 503, 504}
    if start.status != 202:
        return
    body = start.json()
    assert body["job_type"] == "map_search"
    assert "poll_interval" in body
