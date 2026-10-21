"""Live EEA coverage rejection and mixed-layer retention in one observed session."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect

from tests.e2e.helpers.artifacts import ensure_test_artifact_dirs, write_snapshot
from tests.e2e.helpers.network_capture import observed_page
from tests.e2e.test_live_raster_diagnostics import (
    _RasterCapture,
    _read_conversation_id,
    _read_latest_run_trace,
)
from tests.e2e.test_route_matrix_live import _scenario_result


###############################################################################
def _send(page: Page, prompt: str) -> None:
    previous = page.locator(".chat-message--assistant").count()
    page.get_by_label("Chat message").fill(prompt)
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".chat-message--assistant")).to_have_count(
        previous + 1, timeout=120_000
    )
    expect(page.get_by_role("button", name="Stop generating")).not_to_be_visible(
        timeout=120_000
    )
    page.wait_for_timeout(4000)


###############################################################################
def _session(page: Page, api_base_url: str) -> dict[str, Any]:
    conversation_id = _read_conversation_id(page)
    response = page.request.get(f"{api_base_url}/api/conversations/{conversation_id}")
    assert response.ok
    return response.json()["map_session"]


###############################################################################
def _capabilities(session: dict[str, Any]) -> set[str]:
    return {
        str(overlay.get("capability_id") or overlay.get("capabilityId"))
        for overlay in session["overlay_collection"]["instances"]
    }


###############################################################################
def test_eea_coverage_and_gbif_lifecycle(
    browser: Browser, base_url: str, api_base_url: str, artifact_root: Path
) -> None:
    dirs = ensure_test_artifact_dirs(artifact_root, "EEA-LIFECYCLE")
    capture = _RasterCapture()
    with observed_page(
        browser, capture, dirs["http"] / "lifecycle-capture.json"
    ) as page:
        settings = page.request.get(f"{api_base_url}/api/chat/settings").json()
        assert settings["agent_model_provider"] == "opencode-go"
        assert settings["agent_model_name"] == "deepseek-v4.1-flash"
        page.goto(base_url)
        page.get_by_role("button", name="Start new chat").click()
        steps = (
            (
                "milan",
                "Show noise exposure in Milan.",
                ("eea", "noise"),
            ),
            (
                "chicago",
                "Show EEA noise exposure in Chicago, Illinois.",
                ("eea", "noise"),
            ),
            (
                "gbif_add",
                "Add GBIF species observations around Milan, Italy to this map, retaining the EEA noise overlay.",
                ("gbif", "species"),
            ),
            (
                "eea_remove",
                "Remove only the EEA noise exposure overlay and keep the GBIF species observations visible.",
                ("gbif", "species"),
            ),
        )
        last_good: dict[str, Any] | None = None
        for step_id, prompt, hints in steps:
            _send(page, prompt)
            conversation_id = _read_conversation_id(page)
            trace = _read_latest_run_trace(page, api_base_url, conversation_id)
            session = _session(page, api_base_url) or {}
            screenshot = write_snapshot(page, dirs["screenshots"], step_id)
            result = _scenario_result(
                page, capture, step_id, prompt, "map", hints, screenshot, trace
            )
            result["committed_map"] = {
                "session_id": session.get("session_id"),
                "bounds": session.get("bounds"),
                "revision": session.get("overlay_collection", {}).get("revision"),
                "instances": [
                    {
                        key: instance.get(key)
                        for key in ("instance_id", "capability_id", "label", "visible")
                    }
                    for instance in session.get("overlay_collection", {}).get(
                        "instances", []
                    )
                ],
            }
            result["last_known_good_unchanged"] = (
                session == last_good if step_id == "chicago" else None
            )
            (dirs["reports"] / f"{step_id}.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
            assert session, (
                "No committed map; inspect saved scenario report and capture"
            )
            capabilities = _capabilities(session)
            if step_id == "milan":
                assert "eea_noise_end2022" in capabilities
                assert result["classification"] == "map_render_pass"
                last_good = session
            elif step_id == "chicago":
                assert session == last_good
                assert any(
                    word in result["ui_text"].casefold()
                    for word in ("coverage", "outside", "europe")
                )
                assert not any(
                    item.get("render_status") == "ready"
                    for item in trace["render_preparation"]
                )
            elif step_id == "gbif_add":
                assert "eea_noise_end2022" in capabilities
                assert any("gbif" in capability for capability in capabilities)
                assert result["classification"] == "map_render_pass"
            else:
                assert "eea_noise_end2022" not in capabilities
                assert any("gbif" in capability for capability in capabilities)
                assert result["classification"] == "map_render_pass"
        assert capture.requests_by_host["noise.discomap.eea.europa.eu"] == 0
        assert capture.proxy_requests_by_capability["eea_noise_end2022"] > 0
