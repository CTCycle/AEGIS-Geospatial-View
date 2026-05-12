from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops
from playwright.sync_api import Page, Route, expect

from tests.e2e.helpers.chat_stub_payloads import model_settings_payload

PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Jte8AAAAASUVORK5CYII="
)
BASELINE_ROOT = Path(__file__).with_name("visual_baselines")
DIFF_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "visual_diffs"


def _json_ok(route: Route, payload: dict[str, Any]) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _models_payload() -> dict[str, Any]:
    return {
        "cloud": [
            {
                "id": "gpt-4.1-mini",
                "name": "gpt-4.1-mini",
                "description": "Cloud model",
                "provider": "openai",
                "capabilities": ["chat"],
                "metadata": {},
            }
        ],
        "local": [],
    }


def _turn_payload() -> dict[str, Any]:
    return {
        "request_id": "visual-regression-7901",
        "session_id": 7901,
        "assistant_message": "Loaded visual regression fixture.",
        "turn_contract": {
            "user_text": "show fixture map",
            "task_class": "map_search",
            "location_signals": [],
            "normalized_intent": {
                "intent_id": "visual_fixture_map",
                "intent_label": "Visual fixture map",
                "task_tags": ["map"],
                "intent_tags": ["geospatial"],
                "requires_location": True,
            },
            "temporal_signal": {"mode": "none"},
            "ambiguities": [],
            "parser_confidence": 0.95,
        },
        "decision": {
            "plan": {
                "state": "map_search",
                "intent_id": "visual_fixture_map",
                "basemap_id": "osm_default",
                "overlay_ids": ["visual_fixture_points"],
            }
        },
        "map_session": {
            "center": {"latitude": 41.9028, "longitude": 12.4964},
            "bounds": [12.492, 41.899, 12.500, 41.906],
            "basemap": {
                "id": "osm_default",
                "label": "OpenStreetMap",
                "provider": "osm",
                "type": "tile",
                "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "requires_key": False,
                "attribution": "OpenStreetMap contributors",
            },
            "overlays": [
                {
                    "id": "visual_fixture_points",
                    "label": "Visual fixture points",
                    "provider": "fixture",
                    "type": "geojson",
                    "rendering_mode": "clustered-points",
                    "data_format": "GeoJSON",
                    "geometry_type": "Point",
                    "url": "/api/geospatial/layers/visual_fixture_points/features",
                    "attribution": "AEGIS fixture",
                    "default_opacity": 0.8,
                }
            ],
            "compliance_warnings": [
                "Fixture warning for deterministic visual snapshot coverage."
            ],
        },
        "tool_payload": {
            "execution": "map_search",
            "selected_overlay_ids": ["visual_fixture_points"],
        },
    }


def _setup_stubs(page: Page) -> None:
    page.route(
        re.compile(r".*/api/chat/turn$"), lambda route: _json_ok(route, _turn_payload())
    )
    page.route(
        re.compile(r".*/api/chat/settings$"),
        lambda route: _json_ok(route, model_settings_payload()),
    )
    page.route(
        re.compile(r".*/api/chat/models$"),
        lambda route: _json_ok(route, _models_payload()),
    )
    page.route(
        re.compile(r".*/api/maps/catalog$"),
        lambda route: _json_ok(
            route, {"providers": [], "basemaps": [], "overlays": []}
        ),
    )
    page.route(
        re.compile(r".*/api/maps/basemaps/osm/\d+/\d+/\d+\.png$"),
        lambda route: route.fulfill(
            status=200, content_type="image/png", body=PNG_1X1_TRANSPARENT
        ),
    )
    page.route(
        re.compile(r".*/api/geospatial/layers/visual_fixture_points/features$"),
        lambda route: _json_ok(
            route,
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "poi-1",
                        "properties": {"name": "Fixture POI 1"},
                        "geometry": {"type": "Point", "coordinates": [12.496, 41.902]},
                    },
                    {
                        "type": "Feature",
                        "id": "poi-2",
                        "properties": {"name": "Fixture POI 2"},
                        "geometry": {
                            "type": "Point",
                            "coordinates": [12.498, 41.9035],
                        },
                    },
                ],
            },
        ),
    )


def _assert_visual_baseline(actual_bytes: bytes, baseline_name: str) -> None:
    BASELINE_ROOT.mkdir(parents=True, exist_ok=True)
    DIFF_ROOT.mkdir(parents=True, exist_ok=True)
    baseline_path = BASELINE_ROOT / baseline_name
    if os.getenv("UPDATE_VISUAL_BASELINES") == "1" or not baseline_path.exists():
        baseline_path.write_bytes(actual_bytes)
        if not baseline_path.exists():
            raise AssertionError(f"Failed to write baseline: {baseline_path}")
        if os.getenv("UPDATE_VISUAL_BASELINES") == "1":
            return
        raise AssertionError(
            f"Baseline created at {baseline_path}. Re-run without UPDATE_VISUAL_BASELINES=1."
        )

    actual_path = DIFF_ROOT / f"actual_{baseline_name}"
    actual_path.write_bytes(actual_bytes)
    actual = Image.open(actual_path).convert("RGBA")
    expected = Image.open(baseline_path).convert("RGBA")
    if actual.size != expected.size:
        raise AssertionError(
            f"Visual size mismatch for {baseline_name}: expected {expected.size}, got {actual.size}."
        )
    diff = ImageChops.difference(actual, expected)
    bbox = diff.getbbox()
    if bbox is None:
        return
    diff_pixels = sum(1 for pixel in diff.getdata() if pixel != (0, 0, 0, 0))
    if diff_pixels > 250:
        diff_path = DIFF_ROOT / f"diff_{baseline_name}"
        diff.save(diff_path)
        raise AssertionError(
            f"Visual regression for {baseline_name}: {diff_pixels} pixels differ. See {diff_path}."
        )


def test_map_canvas_matches_visual_baseline(page: Page, base_url: str) -> None:
    _setup_stubs(page)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("show fixture map")
    page.get_by_role("button", name="Send").click()

    map_canvas = page.locator(".maplibregl-canvas")
    expect(map_canvas).to_be_visible(timeout=15000)
    _assert_visual_baseline(map_canvas.screenshot(), "map-canvas.png")


def test_overlay_panel_matches_visual_baseline(page: Page, base_url: str) -> None:
    _setup_stubs(page)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("show fixture map")
    page.get_by_role("button", name="Send").click()

    page_root = page.locator("body")
    _assert_visual_baseline(page_root.screenshot(), "geospatial-page.png")
