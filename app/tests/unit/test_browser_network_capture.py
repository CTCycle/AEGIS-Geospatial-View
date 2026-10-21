"""Prevent truncated browser samples from producing false zero-request proof."""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.helpers.network_capture import NetworkCapture, observed_page
from tests.e2e.test_live_raster_diagnostics import _raster_transport as raster_transport
from tests.e2e.test_route_matrix_live import _raster_transport as route_transport


###############################################################################
def test_request_counts_survive_event_truncation() -> None:
    capture = NetworkCapture(max_events=1)
    capture._append(
        {
            "kind": "response",
            "url": "https://localhost/api/geospatial/tiles/test/1/0/0.png",
        }
    )
    capture._append(
        {
            "kind": "request",
            "transport": "aegis_proxy",
            "capability_id": "eea_noise_end2022",
            "url": "http://localhost/api/geospatial/tiles/eea_noise_end2022/1/0/0.png",
        }
    )
    capture._append(
        {
            "kind": "request",
            "transport": "direct_upstream",
            "url": "https://noise.discomap.eea.europa.eu/tile",
        }
    )
    assert len(capture.events) == 1
    assert capture.summary()["dropped_events"] == 2
    assert capture.requests_by_host["noise.discomap.eea.europa.eu"] == 1
    assert capture.requests_by_transport == {"aegis_proxy": 1, "direct_upstream": 1}
    assert capture.proxy_requests_by_capability == {"eea_noise_end2022": 1}


###############################################################################
@pytest.mark.parametrize("transport", [raster_transport, route_transport])
def test_capture_recognizes_eea_and_fema_relay(transport: Any) -> None:
    for host in ("noise.discomap.eea.europa.eu", "hazards-fema.maps.arcgis.com"):
        assert transport(f"https://{host}/tile") == "direct_upstream"
        assert (
            transport(f"https://{host}/api/geospatial/tiles/test/1/0/0.png")
            == "direct_upstream"
        )


###############################################################################
def test_failed_scenario_saves_capture_and_closes_context(tmp_path: Path) -> None:
    calls: list[str] = []

    ###############################################################################
    class FakePage:

        # -------------------------------------------------------------------------
        def screenshot(self, **kwargs: Any) -> None:
            calls.append("failure_screenshot")

    ###############################################################################
    class FakeContext:

        # -------------------------------------------------------------------------
        def __enter__(self) -> "FakeContext":
            return self

        # -------------------------------------------------------------------------
        def __exit__(self, *args: Any) -> None:
            calls.append("closed")

        # -------------------------------------------------------------------------
        def route(self, *args: Any) -> None:
            calls.append("cache_disabled")

        # -------------------------------------------------------------------------
        def new_page(self) -> FakePage:
            return FakePage()

    ###############################################################################
    class FakeBrowser:

        # -------------------------------------------------------------------------
        def new_context(self, **kwargs: Any) -> FakeContext:
            assert kwargs["service_workers"] == "block"
            return FakeContext()

    ###############################################################################
    class Capture(NetworkCapture):

        # -------------------------------------------------------------------------
        def attach(self, page: Any) -> None:
            calls.append("attached")

    capture = Capture()
    output = tmp_path / "capture.json"
    with pytest.raises(RuntimeError):
        with observed_page(FakeBrowser(), capture, output):  # type: ignore[arg-type]
            calls.append("navigation")
            raise RuntimeError("private response must not enter capture")
    saved = json.loads(output.read_text())
    assert calls == [
        "cache_disabled",
        "attached",
        "navigation",
        "failure_screenshot",
        "closed",
    ]
    assert saved["observation"]["started_at"] <= saved["observation"]["ended_at"]
    assert saved["failure_type"] == "RuntimeError"
    assert "private response" not in output.read_text()
