from __future__ import annotations

from threading import Lock
from typing import Any


###############################################################################
class RealtimeMetrics:
    """Small dependency-free metrics collector for the local realtime process.

    The counters are intentionally process-local because the selected
    deployment is a single backend replica.  The interface is stable so a
    Prometheus/OpenTelemetry adapter can replace it when the deployment grows
    to a shared metrics backend.
    """

    _COUNTER_NAMES = (
        "connections_accepted_total",
        "connections_closed_total",
        "messages_received_total",
        "messages_sent_total",
        "commands_rejected_total",
        "protocol_errors_total",
        "events_delivered_total",
    )

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters = {name: 0 for name in self._COUNTER_NAMES}
        self._active_connections = 0
        self._command_count = 0
        self._command_latency_ms_sum = 0.0
        self._command_latency_ms_max = 0.0

    # -------------------------------------------------------------------------
    def connection_opened(self) -> None:
        with self._lock:
            self._counters["connections_accepted_total"] += 1
            self._active_connections += 1

    # -------------------------------------------------------------------------
    def connection_closed(self) -> None:
        with self._lock:
            self._counters["connections_closed_total"] += 1
            self._active_connections = max(0, self._active_connections - 1)

    # -------------------------------------------------------------------------
    def message_received(self) -> None:
        self.increment("messages_received_total")

    # -------------------------------------------------------------------------
    def message_sent(self) -> None:
        self.increment("messages_sent_total")

    # -------------------------------------------------------------------------
    def command_rejected(self) -> None:
        self.increment("commands_rejected_total")

    # -------------------------------------------------------------------------
    def protocol_error(self) -> None:
        self.increment("protocol_errors_total")

    # -------------------------------------------------------------------------
    def event_delivered(self) -> None:
        self.increment("events_delivered_total")

    # -------------------------------------------------------------------------
    def observe_command_latency(self, milliseconds: float) -> None:
        with self._lock:
            self._command_count += 1
            self._command_latency_ms_sum += max(0.0, milliseconds)
            self._command_latency_ms_max = max(
                self._command_latency_ms_max, milliseconds
            )

    # -------------------------------------------------------------------------
    def increment(self, name: str) -> None:
        with self._lock:
            if name in self._counters:
                self._counters[name] += 1

    # -------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters: dict[str, Any] = dict(self._counters)
            active_connections = self._active_connections
            command_count = self._command_count
            latency_sum = self._command_latency_ms_sum
            latency_max = self._command_latency_ms_max
        counters["active_connections"] = active_connections
        counters["commands_total"] = command_count
        counters["command_latency_ms_avg"] = (
            latency_sum / command_count if command_count else 0.0
        )
        counters["command_latency_ms_max"] = latency_max
        return counters
