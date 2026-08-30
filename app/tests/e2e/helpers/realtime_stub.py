from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from playwright.sync_api import Page, WebSocketRoute


TurnPayloadFactory = Callable[[str, int], dict[str, Any]]


###############################################################################
def _envelope(
    *,
    conversation_id: str,
    message_type: str,
    payload: dict[str, Any],
    message_id: str,
    correlation_id: str | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "protocol_version": 1,
        "type": message_type,
        "message_id": message_id,
        "conversation_id": conversation_id,
        "payload": payload,
    }
    if correlation_id is not None:
        envelope["correlation_id"] = correlation_id
    return json.dumps(envelope)


###############################################################################
def register_realtime_stub(
    page: Page,
    turn_payload_factory: TurnPayloadFactory,
    *,
    conversation_id: str = "conversation-e2e",
    error_message: str | None = None,
) -> None:
    """Stub the active WebSocket transport used by the Angular chat page."""
    run_number = 0

    def handle_socket(socket: WebSocketRoute) -> None:
        nonlocal run_number
        match = re.search(r"/api/conversations/([^/]+)/realtime$", socket.url)
        socket_conversation_id = match.group(1) if match else conversation_id
        socket.send(
            _envelope(
                conversation_id=socket_conversation_id,
                message_type="connection.ready",
                payload={"state": "ready"},
                message_id="server-ready",
            )
        )

        def handle_message(raw_message: str | bytes) -> None:
            nonlocal run_number
            try:
                request = json.loads(raw_message)
            except TypeError, json.JSONDecodeError:
                return
            if not isinstance(request, dict):
                return
            request_type = request.get("type")
            message_id = str(request.get("message_id") or "client-message")
            if request_type == "session.resume":
                socket.send(
                    _envelope(
                        conversation_id=socket_conversation_id,
                        message_type="session.resumed",
                        payload={
                            "state": "idle",
                            "run_id": None,
                            "after_sequence": 0,
                        },
                        message_id="server-resumed",
                    )
                )
                return
            if request_type != "run.start":
                return

            payload = request.get("payload")
            if not isinstance(payload, dict):
                return
            run_number += 1
            run_id = f"stub-run-{run_number}"
            message = str(payload.get("message") or "")
            socket.send(
                _envelope(
                    conversation_id=socket_conversation_id,
                    message_type="run.ack",
                    payload={
                        "command": "run.start",
                        "run_id": run_id,
                        "run_version": 1,
                        "duplicate": False,
                    },
                    message_id=f"server-ack-{run_number}",
                    correlation_id=message_id,
                )
            )

            timestamp = datetime.now(UTC).isoformat()

            def send_event(
                sequence: int,
                event_type: str,
                event_payload: dict[str, Any],
            ) -> None:
                event = {
                    "event_id": f"{run_id}-event-{sequence}",
                    "sequence": sequence,
                    "conversation_id": socket_conversation_id,
                    "run_id": run_id,
                    "run_version": 1,
                    "type": event_type,
                    "timestamp": timestamp,
                    "visibility": "user",
                    "payload": event_payload,
                }
                socket.send(
                    _envelope(
                        conversation_id=socket_conversation_id,
                        message_type="run.event",
                        payload=event,
                        message_id=f"server-event-{run_number}-{sequence}",
                    )
                )

            if error_message is not None:
                send_event(1, "error", {"message": error_message})
                return

            turn_payload = turn_payload_factory(message, run_number)
            send_event(
                1,
                "progress",
                {
                    "stage": "understanding_request",
                    "label": "Understanding the request",
                },
            )
            assistant_message = str(turn_payload.get("assistant_message") or "")
            if assistant_message:
                send_event(
                    2, "assistant_text_completed", {"content": assistant_message}
                )

            completion_payload = {
                key: turn_payload[key]
                for key in (
                    "context_revision",
                    "task_snapshot",
                    "decision",
                    "operation",
                    "map_session",
                    "memory_snapshot",
                    "context_usage",
                )
                if key in turn_payload
            }
            send_event(3 if assistant_message else 2, "completed", completion_payload)

        socket.on_message(handle_message)

    page.route_web_socket(
        re.compile(r".*/api/conversations/[^/]+/realtime$"), handle_socket
    )
