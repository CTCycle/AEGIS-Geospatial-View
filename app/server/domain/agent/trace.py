from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from server.common.time import utc_now


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|credential|password|"
    r"private[_-]?key|secret|session[_-]?token|token|bearer|cookie)",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|credential|password|"
    r"secret|token|bearer)",
    re.IGNORECASE,
)
_MAX_TRACE_DEPTH = 5
_MAX_TRACE_ITEMS = 48
_MAX_TRACE_STRING = 4_096


TraceKind = Literal[
    "run_started",
    "plan_created",
    "plan_revised",
    "iteration_started",
    "iteration_completed",
    "task_transition",
    "tools_available",
    "tool_selected",
    "tool_result",
    "retry",
    "compaction",
    "state_delta",
    "checkpoint",
    "model_usage",
    "stage",
    "completion",
]

###############################################################################
class AgentTraceEvent(BaseModel):
    """Operational trace metadata; never a chain-of-thought transcript."""

    model_config = ConfigDict(extra="forbid")

    kind: TraceKind
    run_id: str
    run_version: int = Field(ge=1)
    sequence: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=utc_now)
    iteration: int | None = Field(default=None, ge=1)
    task_id: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    # These fields are optional top-level indexes for trace consumers.  The
    # bounded operational details remain in ``payload`` so old event readers
    # and the internal event store keep working unchanged.
    redaction: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

###############################################################################
class AgentCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    run_id: str
    conversation_id: str
    run_version: int = Field(ge=1)
    conversation_state: dict[str, Any]
    run_state: dict[str, Any] | None = None
    state_hash: str
    completed_call_fingerprints: list[str] = Field(default_factory=list)
    completion_reason: str | None = None


def redact_trace_value(value: object, *, path: str = "$") -> tuple[object, list[str]]:
    """Return a bounded trace-safe value and the fields redacted from it.

    Tool arguments and normalized provider metadata are operationally useful
    but may contain credentials or signed URLs.  The trace keeps structure and
    references while replacing sensitive leaves.  Raw provider payloads stay
    in the evidence store and are never copied into this projection.
    """

    redacted: list[str] = []

    def visit(item: object, item_path: str, depth: int) -> object:
        if item is None or isinstance(item, (bool, int, float)):
            return item
        if isinstance(item, str):
            if depth >= _MAX_TRACE_DEPTH:
                return "[truncated]"
            if "://" in item and "?" in item:
                safe_url, url_fields = redact_trace_url(item, path=item_path)
                redacted.extend(url_fields)
                return safe_url
            bounded = item[:_MAX_TRACE_STRING]
            if len(item) > _MAX_TRACE_STRING:
                redacted.append(item_path)
            return bounded
        if depth >= _MAX_TRACE_DEPTH:
            redacted.append(item_path)
            return "[truncated]"
        if isinstance(item, dict):
            output: dict[str, object] = {}
            typed_item = cast(dict[object, object], item)
            for index, (key, child) in enumerate(typed_item.items()):
                if index >= _MAX_TRACE_ITEMS:
                    redacted.append(item_path)
                    break
                key_text = str(key)
                child_path = f"{item_path}.{key_text}"
                if _SENSITIVE_KEY.search(key_text):
                    output[key_text] = "<redacted>"
                    redacted.append(child_path)
                    continue
                output[key_text] = visit(child, child_path, depth + 1)
            return output
        if isinstance(item, (list, tuple)):
            output_list: list[object] = []
            typed_item = cast(list[object] | tuple[object, ...], item)
            for index, child in enumerate(typed_item):
                if index >= _MAX_TRACE_ITEMS:
                    redacted.append(item_path)
                    break
                output_list.append(visit(child, f"{item_path}[{index}]", depth + 1))
            return output_list
        return str(item)[:_MAX_TRACE_STRING]

    result = visit(value, path, 0)
    return result, list(dict.fromkeys(redacted))


def redact_trace_url(value: str, *, path: str = "$") -> tuple[str, list[str]]:
    """Redact sensitive query parameters while retaining the URL shape."""

    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(value)
    except ValueError:
        return value[:_MAX_TRACE_STRING], []
    if not parts.query:
        return value[:_MAX_TRACE_STRING], []
    redactions: list[str] = []
    query: list[tuple[str, str]] = []
    for key, query_value in parse_qsl(parts.query, keep_blank_values=True):
        if _SENSITIVE_QUERY_KEY.search(key):
            query.append((key, "<redacted>"))
            redactions.append(f"{path}.query.{key}")
        else:
            query.append((key, query_value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))[:_MAX_TRACE_STRING], redactions


__all__ = [
    "AgentCheckpoint",
    "AgentTraceEvent",
    "TraceKind",
    "redact_trace_url",
    "redact_trace_value",
]
