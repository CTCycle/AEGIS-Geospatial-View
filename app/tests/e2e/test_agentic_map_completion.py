"""Controlled full-pipeline proof for the prepared-map acknowledgment contract.

The transport fixture keeps the model/provider response deterministic while the
browser still renders the real Angular/MapLibre path and reports bounded
rendering evidence back through the real client command queue.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
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
SUPERSEDED_RUN_ID = "controlled-map-run-2"
MAP_SESSION_ID = "rome-earthquake-session"
COLLECTION_REVISION = 7
MAX_EVIDENCE_ITEMS = 64
MAX_EVIDENCE_TEXT = 4000

_SENSITIVE_EVIDENCE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)

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
    run_id: str = RUN_ID,
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
            "event_id": f"{run_id}-event-{sequence}",
            "sequence": sequence,
            "conversation_id": CONVERSATION_ID,
            "run_id": run_id,
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
    "mismatched_ack",
    "duplicate_ack",
    "cancelled",
    "superseded",
    "retry_exhausted",
)


def _tested_commit() -> str:
    configured = os.environ.get("APP_TEST_COMMIT")
    if configured and configured.strip():
        return configured.strip()
    repository_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Could not determine the exact tested commit.")
    return commit


def _sanitize_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(marker in key_text.casefold() for marker in _SENSITIVE_EVIDENCE_KEY_MARKERS):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = _sanitize_evidence(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_evidence(item) for item in value[:MAX_EVIDENCE_ITEMS]]
    if isinstance(value, tuple):
        return [_sanitize_evidence(item) for item in value[:MAX_EVIDENCE_ITEMS]]
    return value


def _bounded_text(value: str) -> str:
    return " ".join(value.split())[:MAX_EVIDENCE_TEXT]


def _capture_console_output(page: Page) -> list[dict[str, str]]:
    console_output: list[dict[str, str]] = []

    def capture_console(message: ConsoleMessage) -> None:
        if message.type in {"error", "warning"} and len(console_output) < MAX_EVIDENCE_ITEMS:
            console_output.append({"type": message.type, "text": _bounded_text(message.text)})

    page.on("console", capture_console)
    return console_output


def _candidate_refs(
    acknowledgments: list[dict[str, Any]],
    synthetic_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    references = [
        {
            "map_session_id": acknowledgment.get("map_session_id"),
            "collection_revision": acknowledgment.get("collection_revision"),
            "run_version": acknowledgment.get("run_version"),
            "status": acknowledgment.get("status"),
        }
        for acknowledgment in acknowledgments
    ]
    references.extend(
        {
            "map_session_id": event.get("map_session_id"),
            "collection_revision": event.get("collection_revision"),
            "run_version": event.get("run_version"),
            "status": event.get("status"),
        }
        for event in synthetic_events
        if event.get("map_session_id") is not None
    )
    for reference_data in references:
        reference = (
            reference_data["map_session_id"],
            reference_data["collection_revision"],
        )
        if reference in seen or reference == (None, None):
            continue
        seen.add(reference)
        candidates.append(
            {
                "map_session_id": reference[0],
                "collection_revision": reference[1],
                "run_version": reference_data["run_version"],
                "status": reference_data["status"],
            }
        )
    return candidates


def _final_run_version(
    acknowledgments: list[dict[str, Any]],
    synthetic_events: list[dict[str, Any]],
) -> int | None:
    for item in reversed(acknowledgments):
        if isinstance(item.get("run_version"), int):
            return item["run_version"]
    for item in reversed(synthetic_events):
        if isinstance(item.get("run_version"), int):
            return item["run_version"]
    return None


def _scenario_evidence(
    *,
    page: Page,
    scenario: str,
    acknowledgments: list[dict[str, Any]],
    synthetic_events: list[dict[str, Any]],
    console_output: list[dict[str, str]],
    screenshot_path: Path,
    final_presentation_status: str | None,
    fixture_state: dict[str, Any],
) -> dict[str, Any]:
    candidates = _candidate_refs(acknowledgments, synthetic_events)
    final_run_version = _final_run_version(acknowledgments, synthetic_events)
    final_map_session_id = candidates[-1]["map_session_id"] if candidates else None
    return {
        "scenario": scenario,
        "run_id": RUN_ID,
        "run_version": final_run_version,
        "final_run_version": final_run_version,
        "map_session_id": final_map_session_id,
        "candidate_map_sessions": candidates,
        "tested_commit": _tested_commit(),
        "acknowledgment_count": len(acknowledgments),
        "acknowledgments": _sanitize_evidence(acknowledgments),
        "ack_payloads": _sanitize_evidence(acknowledgments),
        "synthetic_event_sequence": _sanitize_evidence(synthetic_events[:MAX_EVIDENCE_ITEMS]),
        "final_ui_state_text": _bounded_text(page.locator("body").inner_text()),
        "console_output": _sanitize_evidence(console_output),
        "screenshot": str(screenshot_path),
        "screenshot_path": str(screenshot_path),
        "final_presentation_status": final_presentation_status,
        "rejected_acknowledgments": _sanitize_evidence(
            fixture_state.get("rejected_acknowledgments", [])
        ),
    }


def _controlled_socket(
    page: Page,
    acknowledgments: list[dict[str, Any]],
    *,
    scenario: str = "none",
    synthetic_events: list[dict[str, Any]],
    fixture_state: dict[str, Any],
) -> None:
    map_session = _map_session()
    presentation = _prepared_presentation(map_session)
    sequence = 0
    render_attempt = 0
    active_run_version = 1
    active_run_id = RUN_ID
    current_map_session = map_session
    current_presentation = presentation
    cancelled = False
    deferred_superseded_ack: dict[str, Any] | None = None
    fixture_state.setdefault("rejected_acknowledgments", [])

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
            run_id=active_run_id,
        )
        if run_version is not None:
            effective_run_version = run_version
        else:
            effective_run_version = active_run_version
        if len(synthetic_events) < MAX_EVIDENCE_ITEMS:
            sequence_entry: dict[str, Any] = {
                "sequence": sequence,
                "type": event_type,
                "run_id": active_run_id,
                "run_version": effective_run_version,
            }
            for key in ("code", "collection_revision", "map_session_id", "recovery", "status"):
                if key in payload:
                    sequence_entry[key] = payload[key]
            if event_type == "map_prepared" and isinstance(payload.get("map_session"), dict):
                map_session = payload["map_session"]
                sequence_entry["map_session_id"] = map_session.get("session_id")
                overlay_collection = map_session.get("overlay_collection")
                if isinstance(overlay_collection, dict):
                    sequence_entry["collection_revision"] = overlay_collection.get("revision")
            synthetic_events.append(sequence_entry)
        parsed = json.loads(envelope)
        parsed["payload"]["run_version"] = effective_run_version
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

    def reject_superseded_ack(socket: WebSocketRoute, payload: dict[str, Any]) -> None:
        rejected = deepcopy(payload)
        rejected["rejection_reason"] = "superseded"
        if len(fixture_state["rejected_acknowledgments"]) < MAX_EVIDENCE_ITEMS:
            fixture_state["rejected_acknowledgments"].append(rejected)
        socket.send(
            _envelope(
                message_type="protocol.error",
                payload={
                    "code": "render_ack_rejected",
                    "message": "The render acknowledgment is stale after supersession.",
                    "command": "map.render_ack",
                    "accepted": False,
                    "run_id": payload.get("run_id"),
                    "run_version": payload.get("run_version"),
                },
                message_id="controlled-superseded-render-ack",
            )
        )

    def handle_socket(socket: WebSocketRoute) -> None:
        def handle_message(raw: str | bytes) -> None:
            nonlocal active_run_id, active_run_version, current_map_session, current_presentation, render_attempt, cancelled, deferred_superseded_ack
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
                superseding_new_run = scenario == "superseded" and fixture_state.get("started")
                if superseding_new_run:
                    fixture_state["superseded"] = True
                    active_run_id = SUPERSEDED_RUN_ID
                    active_run_version = 1
                    current_map_session = _map_session_variant(2)
                    current_presentation = _prepared_presentation(current_map_session)
                fixture_state["started"] = True
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "run.start",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": active_run_id,
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
                send_prepared(socket)
                if superseding_new_run:
                    reject_superseded_ack(
                        socket,
                        {
                            "run_id": RUN_ID,
                            "run_version": 1,
                            "map_session_id": map_session.get("session_id"),
                            "collection_revision": map_session.get("overlay_collection", {}).get("revision"),
                        },
                    )
                if deferred_superseded_ack is not None:
                    reject_superseded_ack(socket, deferred_superseded_ack)
                    deferred_superseded_ack = None
                return
            if request_type == "run.cancel" and scenario == "cancelled":
                cancelled = True
                fixture_state["final_presentation_status"] = "failed"
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "run.cancel",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": active_run_id,
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
                fixture_state["superseded"] = True
                active_run_version = 2
                current_map_session = _map_session_variant(2)
                current_presentation = _prepared_presentation(current_map_session)
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "run.steer",
                            "accepted": True,
                            "duplicate": False,
                            "run_id": active_run_id,
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
                if deferred_superseded_ack is not None:
                    reject_superseded_ack(socket, deferred_superseded_ack)
                    deferred_superseded_ack = None
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
            if scenario == "mismatched_ack" and len(acknowledgments) == 1:
                rejected = deepcopy(payload)
                rejected["rejection_reason"] = "mismatched_identity"
                if len(fixture_state["rejected_acknowledgments"]) < MAX_EVIDENCE_ITEMS:
                    fixture_state["rejected_acknowledgments"].append(rejected)
                socket.send(
                    _envelope(
                        message_type="protocol.error",
                        payload={
                            "code": "render_ack_mismatch",
                            "message": "The render acknowledgment identity does not match the prepared map.",
                            "command": "map.render_ack",
                            "accepted": False,
                            "details": {
                                "expected": {
                                    "run_id": active_run_id,
                                    "run_version": active_run_version,
                                    "map_session_id": current_map_session.get("session_id"),
                                    "collection_revision": current_map_session.get("overlay_collection", {}).get("revision"),
                                },
                                "observed": {
                                    "run_id": payload.get("run_id"),
                                    "run_version": payload.get("run_version"),
                                    "map_session_id": payload.get("map_session_id"),
                                    "collection_revision": payload.get("collection_revision"),
                                },
                            },
                        },
                        message_id="controlled-mismatched-render-ack",
                    )
                )
                return
            if scenario == "superseded" and (
                not fixture_state.get("superseded")
            ):
                deferred_superseded_ack = deepcopy(payload)
                return
            if scenario == "superseded" and (
                payload.get("run_id") != active_run_id
                or payload.get("run_version") != active_run_version
                or payload.get("map_session_id")
                != current_map_session.get("session_id")
                or payload.get("collection_revision")
                != current_map_session.get("overlay_collection", {}).get("revision")
            ):
                reject_superseded_ack(socket, payload)
                return
            render_attempt += 1
            if scenario == "stale_ack":
                fixture_state["final_presentation_status"] = "failed"
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
                            "run_id": active_run_id,
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
                            "run_id": active_run_id,
                            "run_version": active_run_version,
                            "state": "failed",
                            "presentation_status": "render_timeout",
                        },
                        message_id="controlled-retry-exhausted-ack",
                    )
                )
                fixture_state["final_presentation_status"] = "render_timeout"
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
                        "run_id": active_run_id,
                        "run_version": active_run_version,
                        "state": "completed",
                        "presentation_status": "ready",
                    },
                    message_id="controlled-render-ack",
                )
            )
            fixture_state["final_presentation_status"] = "ready"
            if scenario == "duplicate_ack":
                socket.send(
                    _envelope(
                        message_type="run.ack",
                        payload={
                            "command": "map.render_ack",
                            "accepted": True,
                            "duplicate": True,
                            "run_id": active_run_id,
                            "run_version": active_run_version,
                            "state": "completed",
                            "presentation_status": "ready",
                        },
                        message_id="controlled-duplicate-render-ack",
                    )
                )
            send_event(
                socket,
                "progress",
                {"stage": "completed", "label": "Completed"},
                run_version=active_run_version,
            )
            send_event(
                socket,
                "assistant_text_completed",
                {"content": "Map ready."},
                run_version=active_run_version,
            )
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
                run_version=active_run_version,
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
    synthetic_events: list[dict[str, Any]],
    fixture_state: dict[str, Any],
) -> None:
    def fulfill(route: Route, payload: dict[str, Any]) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    _controlled_socket(
        page,
        acknowledgments,
        scenario=scenario,
        synthetic_events=synthetic_events,
        fixture_state=fixture_state,
    )
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
    synthetic_events: list[dict[str, Any]] = []
    fixture_state: dict[str, Any] = {}
    _setup_controlled_routes(
        page,
        acknowledgments,
        synthetic_events=synthetic_events,
        fixture_state=fixture_state,
    )
    console_output = _capture_console_output(page)
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
    evidence = _scenario_evidence(
        page=page,
        scenario="recent earthquakes around Rome",
        acknowledgments=acknowledgments,
        synthetic_events=synthetic_events,
        console_output=console_output,
        screenshot_path=screenshot_path,
        final_presentation_status=fixture_state.get("final_presentation_status"),
        fixture_state=fixture_state,
    )
    evidence.update(
        {
            "map_session_id": MAP_SESSION_ID,
            "collection_revision": COLLECTION_REVISION,
            "acknowledgment": _sanitize_evidence(acknowledgment),
            "canvas": canvas_box,
            "console_errors": [entry["text"] for entry in console_output if entry["type"] == "error"],
        }
    )
    assert re.fullmatch(r"[0-9a-f]{40}", evidence["tested_commit"])
    report_path = artifact_root / "reports" / "controlled-map-completion.json"
    report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    assert not [
        entry
        for entry in console_output
        if entry["type"] == "error"
        and any(token in entry["text"].casefold() for token in ("typeerror", "webgl", "map source"))
    ]


@pytest.mark.parametrize("scenario", FAULT_SCENARIOS)
def test_controlled_render_fault_scenarios_are_observable_and_bounded(
    page: Page,
    base_url: str,
    artifact_root: Path,
    save_snapshot,
    request: pytest.FixtureRequest,
    scenario: str,
) -> None:
    """Exercise browser-visible render faults without production fault flags.

    The WebSocket route is the only injector.  MapLibre still renders the
    actual candidate and emits the real client acknowledgment; the fixture
    controls only the server response/observation that follows it.
    """

    acknowledgments: list[dict[str, Any]] = []
    synthetic_events: list[dict[str, Any]] = []
    fixture_state: dict[str, Any] = {}
    _setup_controlled_routes(
        page,
        acknowledgments,
        scenario=scenario,
        synthetic_events=synthetic_events,
        fixture_state=fixture_state,
    )
    console_output = _capture_console_output(page)

    def save_controlled_evidence() -> None:
        screenshot_path = save_snapshot(page, f"controlled-map-{scenario}")
        report_path = artifact_root / "reports" / f"controlled-map-{scenario}.json"
        evidence = _scenario_evidence(
            page=page,
            scenario=scenario,
            acknowledgments=acknowledgments,
            synthetic_events=synthetic_events,
            console_output=console_output,
            screenshot_path=screenshot_path,
            final_presentation_status=fixture_state.get("final_presentation_status"),
            fixture_state=fixture_state,
        )
        evidence["fault_injection"] = "WebSocket fixture only"
        report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    request.addfinalizer(save_controlled_evidence)
    page.goto(base_url)
    composer = page.get_by_label("Chat message")
    composer.fill("Show recent earthquakes around Rome")
    page.get_by_role("button", name="Send message").click()

    if scenario == "superseded":
        # Wait for the first run identity before steering it.  The map
        # candidate may already be prepared by this point; the fixture holds
        # its acknowledgement until the superseding command arrives so both
        # event orderings are exercised deterministically.
        expect(page.get_by_role("button", name="Stop generating")).to_be_visible(timeout=15000)
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
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "The map renderer did not produce a verified result.", timeout=15000
        )
        assert len(acknowledgments) == 3
        assert "Map ready." not in page.locator(".chat-message--assistant").all_inner_texts()[-1]
        assert "Map data ready; rendering" not in _bounded_text(page.locator("body").inner_text())
        assert page.get_by_role("button", name="Stop generating").count() == 0
    elif scenario == "stale_ack":
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "real-time connection", timeout=15000
        )
        assert len(acknowledgments) == 1
        assert "Map ready." not in page.locator(".chat-message--assistant").all_inner_texts()[-1]
        assert "Map data ready; rendering" not in _bounded_text(page.locator("body").inner_text())
        assert page.get_by_role("button", name="Stop generating").count() == 0
    elif scenario == "mismatched_ack":
        expect(page.locator(".maplibregl-canvas").last).to_be_visible(timeout=15000)
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "Map ready.", timeout=15000
        )
        assert len(acknowledgments) >= 2
        rejected = fixture_state.get("rejected_acknowledgments", [])
        assert rejected and rejected[0].get("rejection_reason") == "mismatched_identity"
        assert fixture_state.get("final_presentation_status") == "ready"
    elif scenario == "cancelled":
        assistant_messages = page.locator(".chat-message--assistant").all_inner_texts()
        assert assistant_messages and assistant_messages[-1] != "Map ready."
        assert "Map data ready; rendering" not in _bounded_text(page.locator("body").inner_text())
        assert page.get_by_role("button", name="Stop generating").count() == 0
    elif scenario == "superseded":
        expect(page.locator(".maplibregl-canvas").last).to_be_visible(timeout=15000)
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "Map ready.", timeout=15000
        )
        assert acknowledgments
        assert any(
            item.get("run_id") == SUPERSEDED_RUN_ID and item.get("run_version") == 1
            for item in acknowledgments
        ) or any(
            item.get("run_id") == RUN_ID and item.get("run_version") == 2
            for item in acknowledgments
        )
        rejected = fixture_state.get("rejected_acknowledgments", [])
        assert rejected and rejected[0].get("rejection_reason") == "superseded"
        assert any(
            event.get("type") == "map_prepared"
            and (
                (event.get("run_id") == SUPERSEDED_RUN_ID and event.get("run_version") == 1)
                or (event.get("run_id") == RUN_ID and event.get("run_version") == 2)
            )
            for event in synthetic_events
        )
    else:
        expect(page.locator(".maplibregl-canvas").last).to_be_visible(timeout=15000)
        expect(page.locator(".chat-message--assistant").last).to_contain_text(
            "Map ready.", timeout=15000
        )

    assert re.fullmatch(r"[0-9a-f]{40}", _tested_commit())

def test_controlled_evidence_resolves_an_exact_commit() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", _tested_commit())
