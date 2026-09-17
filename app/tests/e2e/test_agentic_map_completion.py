"""Controlled full-pipeline proof for the prepared-map acknowledgment contract.

The transport fixture keeps the model/provider response deterministic while the
browser still renders the real Angular/MapLibre path and reports bounded
rendering evidence back through the real client command queue.
"""

from __future__ import annotations

import base64
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import ConsoleMessage, Page, Route, WebSocketRoute, expect

from tests.e2e.helpers.chat_stub_payloads import (
    ROME_MAP_SESSION,
    _native_goal,
    _native_route,
    conversation_snapshot_payload,
    geospatial_catalog_payload,
    map_overlay_instance,
    model_settings_payload,
)


CONVERSATION_ID = "conversation-controlled-map"
RUN_ID = "controlled-map-run-1"
MAP_SESSION_ID = "rome-earthquake-session"
COLLECTION_REVISION = 7

# A small opaque but visible raster fixture.  The meaningful geographic proof
# is the inline GeoJSON feature; this tile keeps the basemap visibly non-empty
# without depending on an external tile provider.
VISIBLE_TILE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAABbUlEQVR4nMWWsW7CMBCGD4vJ4hk6M0YMTJ36BEx9gCjqECGGioEpQ+aqQ4UYkMUD8BBMnRgsj8x9BuS5AivuxUkcOzbqP4AdxP/p7nwXjxabBVTKnqbs5wJRRbC7/oyosfrarj8BQBz3eh2u5cd7LQIthYklgjfJ61t0BjH2mvEogFasIEjzUdxEkdanURIlaSlp2ZkixRCDgkh313R3VetOgJbwYWBrAKCysAG8ipHWrQ/5hMrir5MtDIHct9O5WiwvZ2yN/3LIJ3jbAzCss9kMb/nqZLF2rUFSJUq7G2tl3eruGsF3wQxHxWBfLzhXreqPIFD/DUjvh4+vToxz4yfGeW9+bDUwDh/cHXUlmjwPQPu5zs+4D57LzHFe1QD2loGqv7yGx9jRuilx3LsEQdRQdWmZYTOKeFkPeGHcAFQW7ta+LwyihmqIhJUR1MmJQzFCR0XSV4xos0h0BDHCt+vB0lfm5uU8TgSWS/8v7kOV+6oVKA8AAAAASUVORK5CYII="
)

###############################################################################
def _envelope(
    *,
    message_type: str,
    payload: dict[str, Any],
    message_id: str,
    sequence: int | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "protocol_version": 1,
        "type": message_type,
        "message_id": message_id,
        "conversation_id": CONVERSATION_ID,
        "payload": payload,
    }
    if sequence is not None:
        envelope["payload"] = {
            "event_id": f"{RUN_ID}-event-{sequence}",
            "sequence": sequence,
            "conversation_id": CONVERSATION_ID,
            "run_id": RUN_ID,
            "run_version": 1,
            "type": payload.pop("type"),
            "timestamp": "2026-09-05T12:00:00Z",
            "visibility": "user",
            "payload": payload,
        }
    return json.dumps(envelope)

###############################################################################
def _map_session() -> dict[str, Any]:
    session = deepcopy(ROME_MAP_SESSION)
    session["session_id"] = MAP_SESSION_ID
    session["bounds"] = [12.3, 41.8, 12.7, 42.0]
    session["overlay_collection"] = {
        "collection_id": "controlled-earthquakes",
        "revision": COLLECTION_REVISION,
        "instances": [
            map_overlay_instance(
                instance_id="earthquake-rome-1",
                capability_id="usgs_earthquakes",
                label="Recent earthquake",
                provider="usgs",
                overlay_type="geojson",
                rendering_mode="geojson",
                descriptor={
                    "layer_id": "earthquake-rome-1",
                    "rendering_mode": "geojson",
                    "source_protocol": "geojson",
                    "data_format": "GeoJSON",
                    "geometry_type": "Point",
                    "result_type": "feature_collection",
                    "data": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "id": "usgs-rome-1",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [12.4964, 41.9028],
                                },
                                "properties": {
                                    "mag": 4.8,
                                    "place": "Rome test fixture",
                                },
                            }
                        ],
                    },
                },
            )
        ],
    }
    return session

###############################################################################
def _prepared_presentation(map_session: dict[str, Any]) -> dict[str, Any]:
    session_id = str(map_session["session_id"])
    collection_revision = int(map_session["overlay_collection"]["revision"])
    return {
        "status": "pending",
        "map_session_id": session_id,
        "collection_revision": collection_revision,
        "required_render_checks": {
            "required_sources_loaded": True,
            "required_layers_present": True,
            "viewport_valid": True,
        },
        "required_overlay_ids": ["earthquake-rome-1"],
        "completion_requirements": [
            {
                "name": "renderable_geometry_created",
                "required": True,
                "status": "satisfied",
            }
        ],
        "pending_response": {
            "assistant_message": "Map ready.",
            "map_session": map_session,
        },
    }

###############################################################################
def _map_session_variant(attempt: int) -> dict[str, Any]:
    session = _map_session()
    session["session_id"] = f"{MAP_SESSION_ID}-attempt-{attempt}"
    session["overlay_collection"]["revision"] = COLLECTION_REVISION + attempt
    return session


FAULT_SCENARIOS = (
    "failed_layer",
    "viewport_mismatch",
    "stale_ack",
    "duplicate_ack",
    "cancelled",
    "superseded",
    "retry_exhausted",
)


def _controlled_socket(
    page: Page,
    acknowledgments: list[dict[str, Any]],
    *,
    scenario: str = "none",
) -> None:
    map_session = _map_session()
    presentation = _prepared_presentation(map_session)
    sequence = 0
    render_attempt = 0
    active_run_version = 1
    current_map_session = map_session
    current_presentation = presentation
    cancelled = False

    def send_event(
        socket: WebSocketRoute,
        event_type: str,
        payload: dict[str, Any],
        *,
        run_version: int | None = None,
    ) -> None:
        nonlocal sequence
        sequence += 1
        event_payload = {"type": event_type, **payload}
        envelope = _envelope(
            message_type="run.event",
            payload=event_payload,
            message_id=f"controlled-event-{sequence}",
            sequence=sequence,
        )
        if run_version is not None:
            parsed = json.loads(envelope)
            parsed["payload"]["run_version"] = run_version
            envelope = json.dumps(parsed)
        socket.send(envelope)

    def send_prepared(socket: WebSocketRoute) -> None:
        send_event(
            socket,
            "map_prepared",
            {
                "presentation": current_presentation,
                "map_session": current_map_session,
                "operation": {
                    "kind": "map_session",
                    "status": "pending",
                    "message": "Data prepared; the map is loading.",
                },
            },
            run_version=active_run_version,
        )

    def handle_socket(socket: WebSocketRoute) -> None:
        def handle_message(raw: str | bytes) -> None:
            nonlocal active_run_version, current_map_session, current_presentation, render_attempt, cancelled
            try:
                request = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return
            if not isinstance(request, dict):
                return
            request_type = request.get("type")
            if request_type == "session.resume":
                socket.send(
                    _envelope(
                        message_type="session.resumed",
                        payload={"state": "idle", "run_id": None, "after_sequence": 0},
                        message_id="controlled-resumed",
                    )
                )
                return
            if request_type == "run.start":
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "run.start",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": RUN_ID,
                            "run_version": active_run_version,
                            "state": "running",
                        },
                        message_id="controlled-start-ack",
                    )
                )
                send_event(
                    socket,
                    "progress",
                    {"stage": "understanding_request", "label": "Understanding the request"},
                )
                send_event(socket, "assistant_text_completed", {"content": "Data prepared; the map is loading."})
                if scenario != "superseded":
                    send_prepared(socket)
                return
            if request_type == "run.cancel" and scenario == "cancelled":
                cancelled = True
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "run.cancel",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": RUN_ID,
                            "run_version": active_run_version,
                            "state": "cancelled",
                            "presentation_status": "failed",
                        },
                        message_id="controlled-cancel-ack",
                    )
                )
                send_event(socket, "cancelled", {"message": "Map update cancelled."})
                return
            if request_type == "run.steer" and scenario == "superseded":
                active_run_version = 2
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "run.steer",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": RUN_ID,
                            "run_version": active_run_version,
                            "state": "running",
                        },
                        message_id="controlled-steer-ack",
                    )
                )
                send_event(
                    socket,
                    "request_updated",
                    {"label": "Request updated"},
                    run_version=active_run_version,
                )
                send_prepared(socket)
                return
            if request_type != "map.render_ack":
                return
            payload = request.get("payload")
            if not isinstance(payload, dict):
                return
            acknowledgments.append(deepcopy(payload))
            if scenario == "cancelled":
                if not cancelled:
                    return
                socket.send(
                    _envelope(
                        message_type="protocol.error",
                        payload={
                            "code": "render_ack_rejected",
                            "message": "The render acknowledgment arrived after cancellation.",
                            "command": "map.render_ack",
                            "accepted": False,
                        },
                        message_id="controlled-cancelled-render-ack",
                    )
                )
                return
            render_attempt += 1
            if scenario == "stale_ack":
                socket.send(
                    _envelope(
                        message_type="protocol.error",
                        payload={
                            "code": "render_ack_rejected",
                            "message": "The render acknowledgment is stale.",
                            "command": "map.render_ack",
                            "accepted": False,
                        },
                        message_id="controlled-stale-ack",
                    )
                )
                return
            if scenario in {"failed_layer", "viewport_mismatch"} and render_attempt == 1:
                failure_code = (
                    "required_layer_not_visible"
                    if scenario == "failed_layer"
                    else "viewport_mismatch"
                )
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "map.render_ack",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": RUN_ID,
                            "run_version": active_run_version,
                            "state": "pending",
                            "presentation_status": "pending",
                        },
                        message_id="controlled-failed-render-ack",
                    )
                )
                send_event(
                    socket,
                    "render_observed",
                    {
                        "map_session_id": payload.get("map_session_id"),
                        "collection_revision": payload.get("collection_revision"),
                        "attempt": render_attempt,
                        "status": "failed",
                        "failure_code": failure_code,
                        "failure_summary": "The controlled fixture rejected this render.",
                        "checks": {
                            "required_sources_loaded": True,
                            "required_layers_present": scenario != "failed_layer",
                            "viewport_valid": scenario != "viewport_mismatch",
                        },
                        "overlay_results": [
                            {
                                "overlay_id": "earthquake-rome-1",
                                "source_loaded": True,
                                "layer_present": scenario != "failed_layer",
                                "visibility_matches": scenario != "failed_layer",
                            }
                        ],
                        "recovery": "revise_map",
                    },
                    run_version=active_run_version,
                )
                current_map_session = _map_session_variant(1)
                current_presentation = _prepared_presentation(current_map_session)
                send_prepared(socket)
                return
            if scenario == "retry_exhausted" and render_attempt <= 3:
                if render_attempt < 3:
                    send_event(
                        socket,
                        "render_observed",
                        {
                            "map_session_id": payload.get("map_session_id"),
                            "collection_revision": payload.get("collection_revision"),
                            "attempt": render_attempt,
                            "status": "failed",
                            "failure_code": "controlled_render_failure",
                            "failure_summary": "The controlled fixture rejected this render.",
                            "checks": {
                                "required_sources_loaded": True,
                                "required_layers_present": False,
                                "viewport_valid": True,
                            },
                            "overlay_results": [
                                {
                                    "overlay_id": "earthquake-rome-1",
                                    "source_loaded": True,
                                    "layer_present": False,
                                    "visibility_matches": False,
                                }
                            ],
                            "recovery": "alternate_source",
                        },
                        run_version=active_run_version,
                    )
                    current_map_session = _map_session_variant(render_attempt)
                    current_presentation = _prepared_presentation(current_map_session)
                    send_prepared(socket)
                    return
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "map.render_ack",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": RUN_ID,
                            "run_version": active_run_version,
                            "state": "failed",
                            "presentation_status": "render_timeout",
                        },
                        message_id="controlled-retry-exhausted-ack",
                    )
                )
                send_event(
                    socket,
                    "error",
                    {
                        "code": "render_retry_exhausted",
                        "message": "The map renderer did not produce a verified result.",
                        "presentation_status": "render_timeout",
                    },
                    run_version=active_run_version,
                )
                return
            socket.send(
                _envelope(
                    message_type="run.ack",
                    payload={
                        "command": "map.render_ack",
                        "accepted": True,
                        "duplicate": False,
                        "run_id": RUN_ID,
                        "run_version": active_run_version,
                        "state": "completed",
                        "presentation_status": "ready",
                    },
                    message_id="controlled-render-ack",
                )
            )
            if scenario == "duplicate_ack":
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "map.render_ack",
                            "accepted": True,
                            "duplicate": True,
                            "run_id": RUN_ID,
                            "run_version": active_run_version,
                            "state": "completed",
                            "presentation_status": "ready",
                        },
                        message_id="controlled-duplicate-render-ack",
                    )
                )
            send_event(socket, "progress", {"stage": "completed", "label": "Completed"})
            send_event(socket, "assistant_text_completed", {"content": "Map ready."})
            send_event(
                socket,
                "completed",
                {
                    "context_revision": 6,
                    "operation": {
                        "kind": "map_session",
                        "status": "success",
                        "message": "Map ready.",
                    },
                    "map_session": current_map_session,
                    "route": _native_route(
                        task_mode="execute",
                        presentation="map",
                        operation="render",
                        requires_location=True,
                        capability_query="earthquakes",
                        target_refs=["location:rome"],
                    ),
                    "goal": _native_goal(
                        task_mode="execute",
                        presentation="map",
                        operation="render",
                        requires_location=True,
                        goal="Show recent earthquakes around Rome",
                    ),
                    "completion_contract": {
                        "operation": "render",
                        "requirements": ["answer_provided", "map_prepared"],
                        "location_required": True,
                        "evidence_required": False,
                        "map_preparation_required": True,
                        "temporal_scope_required": False,
                        "spatial_scope_required": True,
                    },
                    "memory_snapshot": {"active_visualization": current_map_session},
                    "presentation_status": "ready",
                    "tool_results": [],
                    "execution_trace": {"stopped_reason": "goal_satisfied"},
                },
            )

        socket.send(
            _envelope(
                message_type="connection.ready",
                payload={"state": "ready"},
                message_id="controlled-ready",
            )
        )
        socket.on_message(handle_message)

    page.route_web_socket(
        re.compile(r".*/api/conversations/[^/]+/realtime$"), handle_socket
    )

###############################################################################
def _setup_controlled_routes(
    page: Page,
    acknowledgments: list[dict[str, Any]],
    *,
    scenario: str = "none",
) -> None:
    def fulfill(route: Route, payload: dict[str, Any]) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    _controlled_socket(page, acknowledgments, scenario=scenario)
    page.route(
        re.compile(r".*/api/chat/settings$"),
        lambda route: fulfill(route, model_settings_payload()),
    )
    page.route(
        re.compile(r".*/api/chat/models$"),
        lambda route: fulfill(route, {"cloud": [], "local": [], "sources": {}}),
    )
    page.route(
        re.compile(r".*/api/chat/models/ollama/health$"),
        lambda route: fulfill(
            route,
            {"ok": None, "detail": "Controlled fixture does not start Ollama."},
        ),
    )
    page.route(
        re.compile(r".*/api/geospatial/capabilities$"),
        lambda route: fulfill(route, geospatial_catalog_payload()),
    )
    page.route(
        re.compile(r".*/api/conversations/[^/]+$"),
        lambda route: fulfill(route, conversation_snapshot_payload(map_session=None)),
    )
    page.route(
        re.compile(r".*/api/conversations$"),
        lambda route: fulfill(
            route,
            {"conversation_id": CONVERSATION_ID, "title": "Controlled map completion"},
        ),
    )
    page.route(
        "**/api/geospatial/tiles/osm_default/**",
        lambda route: route.fulfill(status=200, content_type="image/png", body=VISIBLE_TILE),
    )

###############################################################################
def test_controlled_map_completion_requires_and_records_visible_rendering(
    page: Page,
    base_url: str,
    artifact_root: Path,
    save_snapshot,
) -> None:
    acknowledgments: list[dict[str, Any]] = []
    _setup_controlled_routes(page, acknowledgments)
    console_errors: list[str] = []

    def capture_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            console_errors.append(message.text)

    page.on("console", capture_console)
    page.goto(base_url)
    page.get_by_label("Chat message").fill("Show recent earthquakes around Rome")
    page.get_by_role("button", name="Send message").click()

    expect(page.get_by_role("status").first).to_contain_text(
        "Map data ready; rendering", timeout=15000
    )
    expect(page.locator(".maplibregl-canvas").last).to_be_visible(timeout=15000)
    for _ in range(150):
        if acknowledgments:
            break
        page.wait_for_timeout(100)
    assert acknowledgments, "MapLibre never sent a render acknowledgment"

    acknowledgment = acknowledgments[0]
    assert acknowledgment["run_id"] == RUN_ID
    assert acknowledgment["map_session_id"] == MAP_SESSION_ID
    assert acknowledgment["collection_revision"] == COLLECTION_REVISION
    assert acknowledgment["status"] == "ready"
    assert acknowledgment["checks"] == {
        "required_sources_loaded": True,
        "required_layers_present": True,
        "viewport_valid": True,
    }
    overlay_results = acknowledgment["overlay_results"]
    assert overlay_results[0]["overlay_id"] == "earthquake-rome-1"
    assert overlay_results[0]["rendered_feature_count"] >= 1

    canvas_box = page.locator(".maplibregl-canvas").last.bounding_box()
    assert canvas_box is not None
    assert canvas_box["width"] > 0 and canvas_box["height"] > 0
    # The status strip is intentionally hidden once the run is terminal; the
    # final assistant message and the committed MapLibre canvas are the durable
    # user-visible completion signals.
    expect(page.locator(".chat-message--assistant").last).to_contain_text("Map ready.")

    screenshot_path = save_snapshot(page, "controlled-map-completed")
    evidence = {
        "scenario": "recent earthquakes around Rome",
        "run_id": RUN_ID,
        "run_version": 1,
        "map_session_id": MAP_SESSION_ID,
        "collection_revision": COLLECTION_REVISION,
        "acknowledgment": acknowledgment,
        "canvas": canvas_box,
        "screenshot": str(screenshot_path),
        "console_errors": console_errors,
    }
    report_path = artifact_root / "reports" / "controlled-map-completion.json"
    report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    assert not [
        error
        for error in console_errors
        if any(token in error.casefold() for token in ("typeerror", "webgl", "map source"))
    ]


@pytest.mark.parametrize("scenario", FAULT_SCENARIOS)
def test_controlled_render_fault_scenarios_are_observable_and_bounded(
    page: Page,
    base_url: str,
    artifact_root: Path,
    save_snapshot,
    scenario: str,
) -> None:
    """Exercise browser-visible render faults without production fault flags.

    The WebSocket route is the only injector.  MapLibre still renders the
    actual candidate and emits the real client acknowledgment; the fixture
    controls only the server response/observation that follows it.
    """

    acknowledgments: list[dict[str, Any]] = []
    _setup_controlled_routes(page, acknowledgments, scenario=scenario)
    page.goto(base_url)
    composer = page.get_by_label("Chat message")
    composer.fill("Show recent earthquakes around Rome")
    page.get_by_role("button", name="Send message").click()

    if scenario == "superseded":
        expect(page.get_by_role("status").first).to_contain_text(
            "Understanding", timeout=15000
        )
        composer.fill("Focus on Milan instead")
        composer.press("Enter")
    elif scenario == "cancelled":
        expect(page.get_by_role("status").first).to_contain_text(
            "Map data ready; rendering", timeout=15000
        )
        page.get_by_role("button", name="Stop generating").click()
    else:
        expect(page.get_by_role("status").first).to_contain_text(
            "Map data ready; rendering", timeout=15000
        )

    if scenario in {"failed_layer", "viewport_mismatch", "duplicate_ack"}:
        expect(page.locator(".maplibregl-canvas").last).to_be_visible(timeout=15000)
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "Map ready.", timeout=15000
        )
        assert len(acknowledgments) >= (2 if scenario != "duplicate_ack" else 1)
    elif scenario == "retry_exhausted":
        expect(page.get_by_role("status").first).to_contain_text(
            "Agent needs attention", timeout=15000
        )
        assert len(acknowledgments) == 3
    elif scenario == "stale_ack":
        expect(page.get_by_role("status").first).to_contain_text(
            "Agent ready", timeout=15000
        )
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "real-time connection", timeout=15000
        )
        assert len(acknowledgments) == 1
    elif scenario == "cancelled":
        expect(page.get_by_role("status").first).to_contain_text(
            "Agent ready", timeout=15000
        )
        assert page.locator(".chat-message--assistant").last.inner_text() != "Map ready."
    else:
        expect(page.locator(".maplibregl-canvas").last).to_be_visible(timeout=15000)
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "Map ready.", timeout=15000
        )

    screenshot_path = save_snapshot(page, f"controlled-map-{scenario}")
    report_path = artifact_root / "reports" / f"controlled-map-{scenario}.json"
    report_path.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "run_id": RUN_ID,
                "acknowledgment_count": len(acknowledgments),
                "acknowledgments": acknowledgments,
                "screenshot": str(screenshot_path),
                "fault_injection": "WebSocket fixture only",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
