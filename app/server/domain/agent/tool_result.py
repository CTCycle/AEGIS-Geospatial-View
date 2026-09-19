"""Canonical model-visible tool result contracts for the native harness."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from server.common.typing import is_json_array, is_json_object


ToolErrorType = Literal[
    "malformed_call",
    "unknown_tool",
    "tool_not_exposed",
    "schema_validation",
    "semantic_validation",
    "policy_rejection",
    "state_conflict",
    "timeout",
    "rate_limit",
    "authentication",
    "provider_unavailable",
    "provider_malformed_response",
    "invalid_tool_output",
    "internal_error",
]
ToolRecovery = Literal[
    "correct_arguments",
    "retry_transport",
    "choose_alternate_tool",
    "replan",
    "request_user_input",
    "terminal",
]
ToolSemanticOutcome = Literal["resolved", "ambiguous", "not_found", "failed"]
type BoundedJson = (
    None
    | bool
    | int
    | float
    | str
    | dict[str, "BoundedJson"]
    | list["BoundedJson"]
)

###############################################################################
class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    code: str
    message: str

###############################################################################
class ToolExecutionError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: ToolErrorType
    code: str
    message: str
    retryable: bool
    recovery: ToolRecovery
    validation_errors: list[ValidationIssue] = Field(
        default_factory=lambda: list[ValidationIssue]()
    )
    upstream_status: int | None = Field(default=None, ge=100, le=599)
    timeout_origin: str | None = None

###############################################################################
class ToolExecutionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str | None = None
    provider_id: str | None = None
    attempt: int = Field(default=1, ge=1)
    duration_ms: int = Field(ge=0)
    api_latency_ms: int | None = Field(default=None, ge=0)
    result_size_bytes: int | None = Field(default=None, ge=0)
    evidence_refs: list[str] = Field(default_factory=lambda: list[str]())
    result_type: str | None = None
    result_status: str | None = None
    stale: bool = False
    fetched_at: str | None = None
    observation_time: str | None = None
    spatial_resolution: str | None = None
    units: dict[str, str] = Field(default_factory=lambda: dict[str, str]())
    coverage: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=lambda: list[str]())
    source_url: str | None = None

###############################################################################
class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    status: Literal["success", "valid_empty", "partial", "failed"]
    summary: str
    semantic_outcome: ToolSemanticOutcome | None = None
    data: dict[str, Any] | list[Any] | None = None
    evidence_refs: list[str] = Field(default_factory=lambda: list[str]())
    map_candidate_id: str | None = None
    error: ToolExecutionError | None = None
    metadata: ToolExecutionMetadata
    truncated: bool = False
    continuation: str | None = None

###############################################################################
class ModelObservation(BaseModel):
    """Bounded observation projected from one application tool result.

    ``ToolResult.data`` may contain a provider payload or a bounded inspection
    page.  It is an application-facing result and is therefore not safe to
    serialize wholesale into the next model request.  This projection keeps
    the semantic result and recovery metadata while applying tool-specific
    limits to the model-visible data.
    """

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    status: Literal["success", "valid_empty", "partial", "failed"]
    summary: str
    semantic_outcome: ToolSemanticOutcome | None = None
    result: dict[str, Any] | list[Any] | None = None
    evidence_refs: list[str] = Field(default_factory=lambda: list[str]())
    provenance: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    warnings: list[str] = Field(default_factory=lambda: list[str]())
    coverage: dict[str, Any] | None = None
    pagination: dict[str, Any] | None = None
    error: ToolExecutionError | None = None
    recovery: ToolRecovery | None = None
    truncated: bool = False
    continuation: str | None = None

    # -------------------------------------------------------------------------
    @classmethod
    def from_tool_result(cls, value: ToolResult, *, max_chars: int = 4096) -> "ModelObservation":
        projected, projected_truncated = _project_result_data(
            value.tool_name,
            value.data,
            max_chars=max(512, int(max_chars)),
        )
        projected_object = projected if is_json_object(projected) else None
        warnings = _bounded_strings(
            projected_object.get("warnings") if projected_object is not None else None,
            limit=8,
            item_chars=300,
        )
        coverage = (
            _bounded_json_value(projected_object.get("coverage"), depth=0, max_depth=3)
            if projected_object is not None
            and is_json_object(projected_object.get("coverage"))
            else None
        )
        pagination = None
        if projected_object is not None:
            raw_pagination = projected_object.get("pagination")
            if is_json_object(raw_pagination):
                pagination = _bounded_json_value(
                    raw_pagination, depth=0, max_depth=3
                )
            elif "next_cursor" in projected_object:
                pagination = {"next_cursor": projected_object.get("next_cursor")}
        metadata = value.metadata.model_dump(mode="json", exclude_none=True)
        provenance = _bounded_json_value(metadata, depth=0, max_depth=3)
        return cls(
            call_id=value.call_id,
            tool_name=value.tool_name,
            status=value.status,
            summary=value.summary[:1000],
            semantic_outcome=value.semantic_outcome,
            result=projected,
            evidence_refs=list(dict.fromkeys(value.evidence_refs))[:16],
            provenance=provenance if is_json_object(provenance) else {},
            warnings=warnings,
            coverage=coverage if is_json_object(coverage) else None,
            pagination=pagination if is_json_object(pagination) else None,
            error=value.error,
            recovery=value.error.recovery if value.error is not None else None,
            truncated=value.truncated or projected_truncated,
            continuation=value.continuation,
        )

###############################################################################
def _project_result_data(
    tool_name: str,
    data: dict[str, Any] | list[Any] | None,
    *,
    max_chars: int,
) -> tuple[dict[str, Any] | list[Any] | None, bool]:
    if data is None:
        return None, False

    if tool_name == "describe_geospatial_capability" and is_json_object(data):
        manifest = data.get("manifest")
        compact_manifest = (
            {
                key: manifest[key]
                for key in (
                    "id",
                    "name",
                    "description",
                    "provider",
                    "type",
                    "capabilityKind",
                    "renderingMode",
                    "coverage",
                    "capabilities",
                    "agenticUse",
                    "reliability",
                )
                if is_json_object(manifest) and key in manifest
            }
            if is_json_object(manifest)
            else None
        )
        projected = {
            "capability_id": data.get("capability_id"),
            "manifest": _bounded_json_value(
                compact_manifest, depth=0, max_depth=4, list_limit=16
            ),
            "argument_schema": _bounded_json_value(
                data.get("argument_schema"), depth=0, max_depth=5, list_limit=32
            ),
            "execution_contract": _bounded_json_value(
                data.get("execution_contract"), depth=0, max_depth=4, list_limit=24
            ),
        }
        return _fit_projection(
            projected,
            max_chars=max_chars,
            preserve_keys=("argument_schema", "execution_contract"),
        )

    # Provider-native layer descriptors and catalog discovery are the result
    # types where removing ``data`` would remove the useful observation
    # entirely. Keep their semantic fields explicit and cap records/contracts
    # before the generic bounded projection runs.
    if tool_name == "discover_geospatial_provider_layers" and is_json_object(data):
        raw_layers = data.get("layers", [])
        layers: list[BoundedJson] = []
        if is_json_array(raw_layers):
            for raw_layer in raw_layers[:20]:
                if not is_json_object(raw_layer):
                    continue
                layer = {
                    key: raw_layer[key]
                    for key in (
                        "provider",
                        "layer_id",
                        "title",
                        "abstract",
                        "rendering_mode",
                        "source_protocol",
                        "data_format",
                        "geometry_type",
                        "queryable",
                        "crs",
                        "formats",
                        "styles",
                        "time_extent",
                        "default_time",
                    )
                    if key in raw_layer
                }
                layers.append(_bounded_json_value(layer, depth=0, max_depth=3))
        projected = {
            "provider": data.get("provider"),
            "layers": layers,
            "next_cursor": data.get("next_cursor"),
            "total": data.get("total"),
            "warnings": _bounded_json_value(
                data.get("warnings", []), depth=0, max_depth=2, list_limit=8
            ),
            "evidence_ref": data.get("evidence_ref"),
        }
        return _fit_projection(projected, max_chars=max_chars, preserve_keys=("layers",))

    # Catalog discovery and evidence inspection are the result types where
    # removing ``data`` would remove the useful observation entirely. Keep
    # their semantic fields explicit and cap records/contracts before the
    # generic bounded projection runs.
    if tool_name == "discover_geospatial_capabilities":
        data_object = data if is_json_object(data) else None
        raw_items = (
            data_object.get(
                "capabilities", data_object.get("items", list[Any]())
            )
            if data_object is not None
            else list[Any]()
        )
        items: list[BoundedJson] = []
        if is_json_array(raw_items):
            for raw_item in raw_items[:12]:
                if not is_json_object(raw_item):
                    continue
                item = {
                    key: raw_item[key]
                    for key in (
                        "id",
                        "name",
                        "description",
                        "provider",
                        "kind",
                        "supports_map",
                        "execution_contract",
                    )
                    if key in raw_item
                }
                items.append(_bounded_json_value(item, depth=0, max_depth=3))
        projected: dict[str, Any] = {
            "capabilities": items,
            "provider_id": data_object.get("provider_id") if data_object else None,
            "next_cursor": data_object.get("next_cursor") if data_object else None,
        }
        if data_object is not None and "items" in data_object:
            projected["items"] = items
        return _fit_projection(projected, max_chars=max_chars, preserve_keys=("capabilities", "items"))

    if tool_name == "inspect_evidence" and is_json_object(data):
        raw_result = data.get("result")
        projected = {
            "evidence_ref": data.get("evidence_ref"),
            "view": data.get("view"),
            "result": _bounded_json_value(
                raw_result,
                depth=0,
                max_depth=4,
                list_limit=20,
            ),
            "source_summary": _bounded_json_value(
                data.get("source_summary"), depth=0, max_depth=3
            ),
        }
        return _fit_projection(projected, max_chars=max_chars, preserve_keys=("result",))

    bounded = _bounded_json_value(data, depth=0, max_depth=4, list_limit=24)
    if not (is_json_object(bounded) or is_json_array(bounded)):
        return None, False
    return _fit_projection(bounded, max_chars=max_chars)


###############################################################################
def _fit_projection(
    value: dict[str, Any] | list[Any] | None,
    *,
    max_chars: int,
    preserve_keys: tuple[str, ...] = (),
) -> tuple[dict[str, Any] | list[Any] | None, bool]:
    bounded = value
    truncated = False
    serialized = json.dumps(bounded, ensure_ascii=True, separators=(",", ":"), default=str)
    if len(serialized) <= max_chars:
        return bounded, False

    # Remove optional dictionary fields in reverse order while preserving the
    # core result field(s).  The loop keeps the value valid JSON at every step.
    if is_json_object(bounded):
        optional_keys = [key for key in bounded if key not in preserve_keys]
        while len(serialized) > max_chars and optional_keys:
            bounded.pop(optional_keys.pop(), None)
            serialized = json.dumps(
                bounded, ensure_ascii=True, separators=(",", ":"), default=str
            )
            truncated = True

    if len(serialized) > max_chars and is_json_object(bounded):
        for key in preserve_keys:
            if key not in bounded:
                continue
            candidate = bounded[key]
            if is_json_array(candidate):
                while len(serialized) > max_chars and len(candidate) > 1:
                    candidate.pop()
                    serialized = json.dumps(
                        bounded, ensure_ascii=True, separators=(",", ":"), default=str
                    )
                    truncated = True
            elif is_json_object(candidate):
                while len(serialized) > max_chars and candidate:
                    candidate.pop(next(reversed(candidate)))
                    serialized = json.dumps(
                        bounded, ensure_ascii=True, separators=(",", ":"), default=str
                    )
                    truncated = True

    if len(serialized) > max_chars:
        # Keep a valid, useful marker rather than cutting a serialized object at
        # an arbitrary character boundary.
        bounded = {
            "truncated": True,
            "available_keys": list(value)[:24] if is_json_object(value) else [],
        }
        truncated = True
    return bounded, truncated


###############################################################################
def _bounded_json_value(
    value: Any,
    *,
    depth: int,
    max_depth: int,
    list_limit: int = 24,
    string_limit: int = 500,
) -> BoundedJson:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:string_limit]
    if depth >= max_depth:
        return "[truncated]"
    if is_json_object(value):
        return {
            str(key): _bounded_json_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                list_limit=list_limit,
                string_limit=string_limit,
            )
            for key, child in list(value.items())[:32]
        }
    if is_json_array(value):
        return [
            _bounded_json_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                list_limit=list_limit,
                string_limit=string_limit,
            )
            for child in list(value)[:list_limit]
        ]
    if isinstance(value, tuple):
        items = list(cast(tuple[Any, ...], value))
        return [
            _bounded_json_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                list_limit=list_limit,
                string_limit=string_limit,
            )
            for child in items[:list_limit]
        ]
    return str(value)[:string_limit]


###############################################################################
def _bounded_strings(value: Any, *, limit: int, item_chars: int) -> list[str]:
    if not is_json_array(value):
        return []
    return [str(item)[:item_chars] for item in value[:limit]]


__all__ = [
    "ModelObservation",
    "ToolExecutionError",
    "ToolExecutionMetadata",
    "ToolResult",
    "ToolRecovery",
    "ToolSemanticOutcome",
    "ToolErrorType",
    "ValidationIssue",
]
