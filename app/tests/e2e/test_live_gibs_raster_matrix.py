"""Browser-authoritative validation matrix for the advertised NASA GIBS rasters."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers.artifacts import ensure_test_artifact_dirs, write_snapshot
from tests.e2e.test_live_raster_diagnostics import (
    _RasterCapture,
    _provider_probe,
    _scenario_result,
)


TEST_ID = "GIBS-RASTER-MATRIX"
GIBS_SCENARIOS = (
    (
        "IMERG_Precipitation_Rate",
        "Show NASA GIBS IMERG precipitation rate over Rome, Italy.",
        True,
    ),
    (
        "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual",
        "Show the NASA GIBS MODIS annual land cover type over Rome, Italy.",
        True,
    ),
    (
        "MODIS_Combined_Thermal_Anomalies_Fire",
        "Show NASA GIBS MODIS thermal anomaly fire observations over Rome, Italy.",
        True,
    ),
    (
        "MODIS_Terra_Aerosol",
        "Show NASA GIBS MODIS Terra aerosol over Rome, Italy.",
        True,
    ),
    (
        "MODIS_Terra_L3_Land_Water_Mask",
        "Show NASA GIBS MODIS Terra land and water mask over Rome, Italy.",
        False,
    ),
    (
        "MODIS_Terra_Land_Surface_Temp_Day",
        "Show NASA GIBS MODIS Terra daytime land surface temperature over Rome, Italy.",
        True,
    ),
    (
        "MODIS_Terra_Land_Surface_Temp_Night",
        "Show NASA GIBS MODIS Terra nighttime land surface temperature over Rome, Italy.",
        True,
    ),
    (
        "MODIS_Terra_NDVI_8Day",
        "Show NASA GIBS MODIS Terra 8-day NDVI vegetation over Rome, Italy.",
        True,
    ),
    (
        "OMPS_Ozone_Total_Column",
        "Show NASA GIBS OMPS total ozone column over Rome, Italy.",
        True,
    ),
    (
        "SRTM_Color_Index",
        "Show the NASA GIBS SRTM color index over Rome, Italy.",
        False,
    ),
    (
        "VIIRS_SNPP_CorrectedReflectance_TrueColor",
        "Show NASA GIBS VIIRS corrected reflectance true color over Rome, Italy.",
        True,
    ),
    (
        "VIIRS_SNPP_DayNightBand_ENCC",
        "Show NASA GIBS VIIRS day-night band ENCC over Rome, Italy.",
        True,
    ),
)


@pytest.mark.parametrize("capability_id,prompt,temporal", GIBS_SCENARIOS)
def test_live_gibs_raster_layer(
    page: Page,
    base_url: str,
    api_base_url: str,
    artifact_root: Path,
    capability_id: str,
    prompt: str,
    temporal: bool,
) -> None:
    """Record each GIBS layer's route, proxy, payload, renderer, and ack boundary."""

    dirs = ensure_test_artifact_dirs(artifact_root, TEST_ID)
    preflight = _provider_probe(page, api_base_url)
    ready = (
        preflight["http_status"] == 200
        and preflight["status"] == "passed"
        and preflight["parse_status"] == "complete"
        and preflight["provider"] == "opencode-go"
        and preflight["model"] == "deepseek-v4.1-flash"
    )
    if not ready:
        (dirs["reports"] / f"{capability_id}.json").write_text(
            json.dumps(
                {
                    "test_id": TEST_ID,
                    "capability_id": capability_id,
                    "temporal": temporal,
                    "provider_probe": preflight,
                    "classification": "provider_lane_unavailable",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        pytest.skip(f"Exact live provider lane was not ready: {preflight}")

    page.goto(base_url)
    page.get_by_role("button", name="Start new chat").click()
    expect(page.locator(".chat-message--assistant")).to_have_count(0)
    capture = _RasterCapture()
    capture.attach(page)
    page.get_by_label("Chat message").fill(prompt)
    page.get_by_role("button", name="Send message").click()
    expect(page.get_by_text(prompt, exact=True)).to_be_visible(timeout=15_000)
    expect(page.locator(".chat-message--assistant").last).to_be_visible(timeout=90_000)
    stop_button = page.get_by_role("button", name="Stop generating")
    if stop_button.count():
        expect(stop_button).not_to_be_visible(timeout=90_000)
    page.wait_for_timeout(5_000)

    screenshot = write_snapshot(page, dirs["screenshots"], capability_id)
    result: dict[str, Any] = _scenario_result(
        page, capture, capability_id, prompt, screenshot
    )
    result.update(
        {
            "provider": "gibs",
            "capability_id": capability_id,
            "temporal": temporal,
            "requested_time": None,
            "effective_time": "provider_default_or_unobserved",
            "provider_descriptor": "unobserved_in_browser",
        }
    )
    (dirs["http"] / f"{capability_id}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (dirs["reports"] / f"{capability_id}.json").write_text(
        json.dumps(
            {
                "test_id": TEST_ID,
                "tested_commit": os.environ.get("APP_TEST_COMMIT", "unknown"),
                "provider_probe": preflight,
                "result": result,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
