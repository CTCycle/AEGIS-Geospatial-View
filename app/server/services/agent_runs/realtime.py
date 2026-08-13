from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import time
from contextlib import suppress
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from server.domain.agent_runs import AgentRunCreateRequest
from server.domain.realtime import (
    MAX_REALTIME_MESSAGE_BYTES,
    REALTIME_PROTOCOL_VERSION,
    REALTIME_SUBPROTOCOL,
    RealtimeCancelPayload,
    RealtimeClientMessage,
    RealtimeResumePayload,
    RealtimeServerMessage,
    RealtimeStartPayload,
    RealtimeSteerPayload,
)
from server.domain.run_events import RunEventType
from server.domain.steering import SteeringMessageRequest
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.conversations import ConversationRepository
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.exceptions import (
    RunAccessError,
    RunConflictError,
    RunNotFoundError,
    RunServiceError,
)
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.metrics import RealtimeMetrics
from server.services.agent_runs.steering import RunSteeringService

LOGGER = logging.getLogger(__name__)

TERMINAL_EVENT_TYPES = {
    RunEventType.COMPLETED,
    RunEventType.CANCELLED,
    RunEventType.ERROR,
    RunEventType.CLARIFICATION_NEEDED,
}

HEARTBEAT_INTERVAL_SECONDS = 15.0
HEARTBEAT_TIMEOUT_SECONDS = 10.0
HANDSHAKE_TIMEOUT_SECONDS = 10.0
OUTBOUND_QUEUE_SIZE = 256
OUTBOUND_ENQUEUE_TIMEOUT_SECONDS = 5.0
MAX_COMMANDS_PER_MINUTE = 60

###############################################################################
class RealtimeConnectionRegistry:
    """Tracks live sockets so shutdown can close them deterministically."""

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self._connections: set[RealtimeConnection] = set()
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    async def add(self, connection: RealtimeConnection) -> None:
        async with self._lock:
            self._connections.add(connection)

    # -------------------------------------------------------------------------
    async def remove(self, connection: RealtimeConnection) -> None:
        async with self._lock:
            self._connections.discard(connection)

    # -------------------------------------------------------------------------
    async def close_all(self) -> None:
        async with self._lock:
            connections = list(self._connections)
        await asyncio.gather(
            *(connection.close(code=1012, reason="server_shutdown") for connection in connections),
            return_exceptions=True,
        )

    # -------------------------------------------------------------------------
    async def count(self) -> int:
        async with self._lock:
            return len(self._connections)

###############################################################################
class RealtimeConnection:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        websocket: WebSocket,
        *,
        conversation_id: str,
        conversation_repository: ConversationRepository,
        run_repository: AgentRunRepository,
        lifecycle_service: RunLifecycleService,
        steering_service: RunSteeringService,
        event_publisher: RunEventPublisher,
        registry: RealtimeConnectionRegistry,
        metrics: RealtimeMetrics | None = None,
    ) -> None:
        self.websocket = websocket
        self.conversation_id = conversation_id
        self.conversation_repository = conversation_repository
        self.run_repository = run_repository
        self.lifecycle_service = lifecycle_service
        self.steering_service = steering_service
        self.event_publisher = event_publisher
        self.registry = registry
        self.metrics = metrics or RealtimeMetrics()
        self._outbound: asyncio.Queue[RealtimeServerMessage] = asyncio.Queue(
            maxsize=OUTBOUND_QUEUE_SIZE
        )
        self._closed = asyncio.Event()
        self._close_lock = asyncio.Lock()
        self._writer_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._active_run_id: str | None = None
        self._last_sequence = 0
        self._last_pong = time.monotonic()
        self._last_ping_nonce: str | None = None
        self._command_times: list[float] = []
        self._first_message_received = False
        self._metrics_opened = False

    # -------------------------------------------------------------------------
    async def run(self) -> None:
        await self.registry.add(self)
        await self.websocket.accept(subprotocol=REALTIME_SUBPROTOCOL)
        self.metrics.connection_opened()
        self._metrics_opened = True
        self._writer_task = asyncio.create_task(self._writer(), name="realtime-writer")
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat(), name="realtime-heartbeat"
        )
        try:
            await self._send(
                "connection.ready",
                payload={
                    "protocol_version": REALTIME_PROTOCOL_VERSION,
                    "connection_id": f"conn_{uuid4().hex}",
                    "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
                    "max_message_bytes": MAX_REALTIME_MESSAGE_BYTES,
                },
            )
            await self._receive_loop()
        except WebSocketDisconnect:
            LOGGER.info(
                "realtime_disconnect conversation_id=%s run_id=%s",
                self.conversation_id,
                self._active_run_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception(
                "realtime_connection_failure conversation_id=%s run_id=%s",
                self.conversation_id,
                self._active_run_id,
            )
            with suppress(Exception):
                await self.close(code=1011, reason="internal_error")
        finally:
            await self.close(code=1000, reason="closed")

    # -------------------------------------------------------------------------
    async def close(self, *, code: int = 1000, reason: str = "closed") -> None:
        async with self._close_lock:
            if self._closed.is_set():
                return
            self._closed.set()
            current = asyncio.current_task()
            tasks = [
                task
                for task in (self._event_task, self._heartbeat_task, self._writer_task)
                if task is not None and task is not current
            ]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(Exception):
                await self.websocket.close(code=code, reason=reason)
            if self._metrics_opened:
                self.metrics.connection_closed()
                self._metrics_opened = False
            await self.registry.remove(self)

    # -------------------------------------------------------------------------
    async def _receive_loop(self) -> None:
        first_deadline = time.monotonic() + HANDSHAKE_TIMEOUT_SECONDS
        while not self._closed.is_set():
            timeout = None
            if not self._first_message_received:
                timeout = max(0.01, first_deadline - time.monotonic())
            try:
                message = (
                    await asyncio.wait_for(self.websocket.receive(), timeout=timeout)
                    if timeout is not None
                    else await self.websocket.receive()
                )
            except TimeoutError:
                await self._protocol_error(None, "handshake_timeout", fatal=True)
                return
            if message.get("type") == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                await self._protocol_error(None, "binary_messages_not_supported", fatal=True)
                return
            if len(text.encode("utf-8")) > MAX_REALTIME_MESSAGE_BYTES:
                await self._protocol_error(None, "message_too_large", fatal=True)
                return
            self._first_message_received = True
            await self._handle_message(text)

    # -------------------------------------------------------------------------
    async def _handle_message(self, text: str) -> None:
        started = time.monotonic()
        self.metrics.message_received()
        try:
            raw = json.loads(text)
            message = RealtimeClientMessage.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, TypeError):
            self.metrics.command_rejected()
            self.metrics.observe_command_latency((time.monotonic() - started) * 1000)
            await self._protocol_error(None, "invalid_message", fatal=False)
            return

        if message.type not in {"heartbeat.ping", "heartbeat.pong"}:
            now = time.monotonic()
            self._command_times = [item for item in self._command_times if now - item < 60]
            if len(self._command_times) >= MAX_COMMANDS_PER_MINUTE:
                self.metrics.command_rejected()
                self.metrics.observe_command_latency((time.monotonic() - started) * 1000)
                await self._protocol_error(message.message_id, "rate_limited", fatal=True)
                return
            self._command_times.append(now)

        try:
            if message.type == "heartbeat.pong":
                self._handle_pong(message.payload)
            elif message.type == "heartbeat.ping":
                await self._send(
                    "heartbeat.pong",
                    correlation_id=message.message_id,
                    payload={"nonce": message.payload.get("nonce")},
                )
            elif message.type == "session.resume":
                await self._resume(message)
            elif message.type == "run.start":
                await self._start_run(message)
            elif message.type == "run.steer":
                await self._steer_run(message)
            elif message.type == "run.cancel":
                await self._cancel_run(message)
        except RunServiceError as exc:
            await self._protocol_error(
                message.message_id,
                self._error_code(exc),
                fatal=False,
                command=message.type,
            )
        except ValidationError:
            await self._protocol_error(
                message.message_id,
                "invalid_payload",
                fatal=False,
                command=message.type,
            )
        except Exception:
            LOGGER.exception(
                "realtime_command_failure conversation_id=%s type=%s",
                self.conversation_id,
                message.type,
            )
            await self._protocol_error(
                message.message_id,
                "command_failed",
                fatal=False,
                command=message.type,
            )
        finally:
            self.metrics.observe_command_latency((time.monotonic() - started) * 1000)

    # -------------------------------------------------------------------------
    async def _resume(self, message: RealtimeClientMessage) -> None:
        payload = RealtimeResumePayload.model_validate(message.payload)
        if payload.run_id is None:
            if self._event_task is not None:
                self._event_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._event_task
                self._event_task = None
            self._active_run_id = None
            self._last_sequence = 0
            await self._send(
                "session.resumed",
                correlation_id=message.message_id,
                payload={"run_id": None, "after_sequence": 0},
            )
            return
        snapshot = self.run_repository.get_run(payload.run_id)
        if snapshot is None or snapshot.conversation_id != self.conversation_id:
            raise RunNotFoundError("Run not found.")
        self._last_sequence = payload.after_sequence
        await self._send(
            "session.resumed",
            correlation_id=message.message_id,
            payload={
                "run_id": payload.run_id,
                "after_sequence": payload.after_sequence,
                "state": snapshot.state.value,
            },
        )
        await self._attach_run(payload.run_id, payload.after_sequence)

    # -------------------------------------------------------------------------
    async def _start_run(self, message: RealtimeClientMessage) -> None:
        payload = RealtimeStartPayload.model_validate(message.payload)
        result, created = await self.lifecycle_service.create_run_with_status(
            self.conversation_id,
            AgentRunCreateRequest(
                message=payload.message,
                client_request_id=payload.client_request_id,
            ),
        )
        await self._send(
            "run.ack",
            correlation_id=message.message_id,
            payload={
                "command": "run.start",
                "accepted": True,
                "duplicate": not created,
                "run_id": result.run_id,
                "run_version": result.run_version,
                "state": result.state.value,
            },
        )
        await self._attach_run(result.run_id, 0 if created else self._last_sequence)

    # -------------------------------------------------------------------------
    async def _steer_run(self, message: RealtimeClientMessage) -> None:
        payload = RealtimeSteerPayload.model_validate(message.payload)
        if self._active_run_id is not None and payload.run_id != self._active_run_id:
            raise RunConflictError("A different run is already active on this connection.")
        response = await self.steering_service.steer(
            self.conversation_id,
            payload.run_id,
            SteeringMessageRequest(
                message=payload.message,
                client_mutation_id=payload.client_mutation_id,
            ),
        )
        await self._send(
            "run.ack",
            correlation_id=message.message_id,
            payload={
                "command": "run.steer",
                "accepted": True,
                "duplicate": response.duplicate,
                "run_id": response.run_id,
                "steering_id": response.steering_id,
                "run_version": response.run_version,
                "state": response.state.value,
            },
        )

    # -------------------------------------------------------------------------
    async def _cancel_run(self, message: RealtimeClientMessage) -> None:
        payload = RealtimeCancelPayload.model_validate(message.payload)
        response, transitioned = await self.lifecycle_service.cancel_run_with_status(
            self.conversation_id,
            payload.run_id,
        )
        await self._send(
            "run.ack",
            correlation_id=message.message_id,
            payload={
                "command": "run.cancel",
                "accepted": True,
                "duplicate": not transitioned,
                "run_id": response.run_id,
                "state": response.state.value,
            },
        )

    # -------------------------------------------------------------------------
    async def _attach_run(self, run_id: str, after_sequence: int) -> None:
        if self._event_task is not None:
            self._event_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._event_task
        self._active_run_id = run_id
        self._last_sequence = max(0, after_sequence)
        self._event_task = asyncio.create_task(
            self._forward_events(run_id, self._last_sequence),
            name=f"realtime-events-{run_id}",
        )

    # -------------------------------------------------------------------------
    async def _forward_events(self, run_id: str, after_sequence: int) -> None:
        terminal_seen = False
        async for event in self.event_publisher.events(
            run_id,
            after_sequence=after_sequence,
        ):
            if self._closed.is_set() or event.conversation_id != self.conversation_id:
                return
            if event.sequence <= self._last_sequence:
                continue
            self._last_sequence = event.sequence
            self.metrics.event_delivered()
            await self._send(
                "run.event",
                payload=event.model_dump(mode="json"),
            )
            if event.type in TERMINAL_EVENT_TYPES:
                terminal_seen = True
                return
        # A publisher queue sentinel means the subscriber was evicted because
        # it could not keep up.  Close the socket so the client reconnects and
        # replays the durable event log from its last acknowledged sequence;
        # silently returning here would strand the connection with lost work.
        if not terminal_seen and not self._closed.is_set():
            await self.close(code=1013, reason="event_replay_required")

    # -------------------------------------------------------------------------
    async def _writer(self) -> None:
        try:
            while not self._closed.is_set():
                message = await self._outbound.get()
                await self.websocket.send_text(
                    json.dumps(message.model_dump(mode="json"), separators=(",", ":"))
                )
                self.metrics.message_sent()
        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            await self.close(code=1001, reason="writer_disconnect")
        except Exception:
            LOGGER.exception(
                "realtime_writer_failure conversation_id=%s run_id=%s",
                self.conversation_id,
                self._active_run_id,
            )
            await self.close(code=1011, reason="writer_failure")

    # -------------------------------------------------------------------------
    async def _heartbeat(self) -> None:
        while not self._closed.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            if time.monotonic() - self._last_pong > HEARTBEAT_INTERVAL_SECONDS + HEARTBEAT_TIMEOUT_SECONDS:
                await self.close(code=4408, reason="heartbeat_timeout")
                return
            nonce = uuid4().hex
            self._last_ping_nonce = nonce
            await self._send("heartbeat.ping", payload={"nonce": nonce})

    # -------------------------------------------------------------------------
    def _handle_pong(self, payload: dict[str, Any]) -> None:
        nonce = payload.get("nonce")
        if self._last_ping_nonce is None or nonce == self._last_ping_nonce:
            self._last_pong = time.monotonic()

    # -------------------------------------------------------------------------
    async def _send(
        self,
        message_type: str,
        *,
        payload: dict[str, Any] | None = None,
        message_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if self._closed.is_set():
            return
        message = RealtimeServerMessage(
            type=message_type,
            message_id=message_id,
            correlation_id=correlation_id,
            conversation_id=self.conversation_id,
            payload=payload or {},
        )
        try:
            await asyncio.wait_for(
                self._outbound.put(message), timeout=OUTBOUND_ENQUEUE_TIMEOUT_SECONDS
            )
        except TimeoutError:
            await self.close(code=1013, reason="outbound_backpressure")

    # -------------------------------------------------------------------------
    async def _protocol_error(
        self,
        correlation_id: str | None,
        code: str,
        *,
        fatal: bool,
        command: str | None = None,
    ) -> None:
        self.metrics.protocol_error()
        payload: dict[str, Any] = {"code": code, "fatal": fatal}
        if command is not None:
            payload["command"] = command
        await self._send(
            "protocol.error",
            correlation_id=correlation_id,
            payload=payload,
        )
        if fatal:
            await self.close(code=1008, reason=code)

    # -------------------------------------------------------------------------
    @staticmethod
    def _error_code(exc: RunServiceError) -> str:
        if isinstance(exc, RunNotFoundError):
            return "run_not_found"
        if isinstance(exc, RunAccessError):
            return "access_denied"
        if isinstance(exc, RunConflictError):
            return "run_conflict"
        return "run_service_failure"

###############################################################################
def is_realtime_origin_allowed(websocket: WebSocket) -> bool:
    """Restrict the unauthenticated local mode to the configured UI origin."""
    configured_host = os.getenv("FASTAPI_HOST", "127.0.0.1").strip().lower()
    try:
        if not ipaddress.ip_address(configured_host).is_loopback and configured_host not in {
            "localhost",
        }:
            return False
    except ValueError:
        if configured_host not in {"localhost"}:
            return False

    origin = websocket.headers.get("origin")
    if not origin:
        return os.getenv("REALTIME_ALLOW_MISSING_ORIGIN", "false").lower() in {
            "1",
            "true",
            "yes",
        }
    ui_host = os.getenv("UI_HOST", "127.0.0.1").strip()
    ui_port = os.getenv("UI_PORT", "8001").strip()
    allowed = {
        f"http://{ui_host}:{ui_port}",
        f"http://localhost:{ui_port}",
        f"http://127.0.0.1:{ui_port}",
    }
    return origin.rstrip("/") in allowed
