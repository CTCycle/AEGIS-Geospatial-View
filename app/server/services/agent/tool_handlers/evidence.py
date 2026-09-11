"""Native-v2 evidence inspection and transformation handlers."""

from __future__ import annotations

import json
import math
import time
from typing import Any

from server.common.typing import is_json_array, is_json_object
from server.domain.agent.capability_route import AgentState
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.services.agent.tool_definitions import (
    InspectEvidenceInput,
    TransformEvidenceInput,
)


###############################################################################
class EvidenceToolHandler:

    # -------------------------------------------------------------------------
    def __init__(self, *, repository: AgentEvidenceRepository) -> None:
        self.repository = repository

    # -------------------------------------------------------------------------
    async def inspect(
        self,
        request: InspectEvidenceInput,
        state: AgentState,
    ) -> ToolResult:
        started = time.perf_counter()
        if request.evidence_ref not in state.evidence_refs:
            return _failure(
                tool_name="inspect_evidence",
                code="unknown_evidence",
                message="The evidence reference is not part of the current state.",
                recovery="choose_alternate_tool",
                started=started,
            )
        item = self.repository.get_payload(
            request.evidence_ref,
            conversation_id=state.conversation_id,
        )
        if item is None:
            return _failure(
                tool_name="inspect_evidence",
                code="unknown_evidence",
                message="The evidence reference is unavailable.",
                recovery="choose_alternate_tool",
                started=started,
            )
        summary, raw = item
        if summary.status == "failed":
            return _failure(
                tool_name="inspect_evidence",
                code="failed_evidence",
                message="The requested evidence is marked as failed.",
                recovery="replan",
                started=started,
            )
        payload = _decode_json(raw)
        data = _inspect_payload(
            payload,
            view=request.view,
            fields=request.fields,
            cursor=request.cursor,
            limit=request.limit,
        )
        return ToolResult(
            call_id="handler-call",
            tool_name="inspect_evidence",
            status="success",
            summary=f"Inspected evidence using the {request.view} view.",
            data={
                "evidence_ref": request.evidence_ref,
                "view": request.view,
                "result": data,
                "source_summary": summary.summary,
            },
            evidence_refs=[request.evidence_ref],
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                evidence_refs=[request.evidence_ref],
            ),
        )

    # -------------------------------------------------------------------------
    async def transform(
        self,
        request: TransformEvidenceInput,
        state: AgentState,
    ) -> ToolResult:
        started = time.perf_counter()
        refs = list(dict.fromkeys(request.evidence_refs))
        if any(ref not in state.evidence_refs for ref in refs):
            return _failure(
                tool_name="transform_evidence",
                code="unknown_evidence",
                message="One or more evidence references are not in the current state.",
                recovery="choose_alternate_tool",
                started=started,
            )
        records: list[dict[str, Any]] = []
        for ref in refs:
            item = self.repository.get_payload(
                ref,
                conversation_id=state.conversation_id,
            )
            if item is None:
                return _failure(
                    tool_name="transform_evidence",
                    code="unknown_evidence",
                    message="One or more evidence references are unavailable.",
                    recovery="choose_alternate_tool",
                    started=started,
                )
            summary, raw = item
            if summary.status == "failed":
                return _failure(
                    tool_name="transform_evidence",
                    code="failed_evidence",
                    message="Failed evidence cannot be transformed.",
                    recovery="replan",
                    started=started,
                )
            records.extend(_records_from_payload(_decode_json(raw)))
        transformed, error = _apply_operations(records, request.operations)
        if error is not None:
            return _failure(
                tool_name="transform_evidence",
                code="invalid_transform",
                message=error,
                recovery="correct_arguments",
                started=started,
            )
        status = "success" if transformed else "valid_empty"
        evidence = self.repository.create(
            conversation_id=state.conversation_id,
            run_id=state.request_id,
            kind="derived",
            media_type="application/json",
            status="available" if transformed else "valid_empty",
            payload={"records": transformed},
            summary={
                "record_count": len(transformed),
                "parent_count": len(refs),
                "map_eligibility": "renderable" if transformed else "not_renderable",
            },
            provenance={"operation_count": len(request.operations)},
            parent_evidence_ids=refs,
        )
        evidence_ref = str(evidence.evidence_id)
        state.evidence_refs.append(evidence_ref)
        return ToolResult(
            call_id="handler-call",
            tool_name="transform_evidence",
            status=status,
            summary=f"Created derived evidence with {len(transformed)} records.",
            data={"record_count": len(transformed), "parent_refs": refs},
            evidence_refs=[evidence_ref],
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                evidence_refs=[evidence_ref],
            ),
        )


###############################################################################
def _decode_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"byte_size": len(raw)}


###############################################################################
def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if is_json_object(payload):
        for key in ("records", "features", "items", "data"):
            value = payload.get(key)
            if is_json_array(value):
                return [item for item in value if is_json_object(item)]
        return [payload]
    return [item for item in payload if is_json_object(item)] if is_json_array(payload) else []


###############################################################################
def _inspect_payload(
    payload: Any,
    *,
    view: str,
    fields: list[str],
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    records = _records_from_payload(payload)
    if fields:
        records = [
            {key: item.get(key) for key in fields if key in item} for item in records
        ]
    if view == "metadata":
        return {
            "type": type(payload).__name__,
            "keys": list(payload)[:100] if is_json_object(payload) else [],
            "record_count": len(records),
        }
    if view == "schema":
        return {
            "fields": sorted({key for item in records for key in item}),
            "record_count": len(records),
        }
    if view == "statistics":
        statistics: dict[str, Any] = {}
        for key in sorted({key for item in records for key in item}):
            values = [
                float(item[key])
                for item in records
                if isinstance(item.get(key), (int, float))
                and not isinstance(item.get(key), bool)
            ]
            if values:
                statistics[key] = {
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
        return {"statistics": statistics, "record_count": len(records)}
    start = int(cursor or 0) if str(cursor or "0").isdigit() else 0
    page = records[start : start + max(1, min(limit, 100))]
    next_cursor = start + len(page)
    return {
        "records": page,
        "pagination": {
            "cursor": str(next_cursor) if next_cursor < len(records) else None,
            "total": len(records),
        },
    }


###############################################################################
def _apply_operations(
    records: list[dict[str, Any]], operations: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str | None]:
    allowed = {
        "attribute_filter",
        "temporal_filter",
        "spatial_filter",
        "sort",
        "limit",
        "field_projection",
        "aggregate",
    }
    result = list(records)
    for operation in operations:
        op = str(operation.get("op") or "")
        if op not in allowed:
            return result, "Only supported declarative evidence operations are allowed."
        if op == "attribute_filter":
            field = str(operation.get("field") or "")
            operator = str(operation.get("operator") or "eq")
            expected = operation.get("value")
            if not field or operator not in {"eq", "neq", "in", "contains", "gte", "lte"}:
                return result, "attribute_filter requires a field and supported operator."
            result = [
                item
                for item in result
                if _matches(item.get(field), operator, expected)
            ]
        elif op == "temporal_filter":
            field = str(operation.get("field") or "timestamp")
            start = str(operation.get("start") or "")
            end = str(operation.get("end") or "")
            if not start and not end:
                return result, "temporal_filter requires a start or end bound."
            result = [
                item
                for item in result
                if isinstance(item.get(field), str)
                and (not start or item[field] >= start)
                and (not end or item[field] <= end)
            ]
        elif op == "sort":
            field = str(operation.get("field") or "")
            if not field:
                return result, "sort requires a field."
            result.sort(
                key=lambda item: (item.get(field) is None, str(item.get(field) or "")),
                reverse=bool(operation.get("descending")),
            )
        elif op == "limit":
            count = operation.get("value")
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 10000:
                return result, "limit must be an integer between 1 and 10000."
            result = result[:count]
        elif op == "field_projection":
            fields = operation.get("fields")
            if not is_json_array(fields) or not fields:
                return result, "field_projection requires a non-empty fields list."
            result = [
                {str(key): item.get(str(key)) for key in fields if str(key) in item}
                for item in result
            ]
        elif op == "aggregate":
            field = str(operation.get("field") or "")
            group_by = str(operation.get("group_by") or "")
            if not field or not group_by:
                return result, "aggregate requires field and group_by."
            groups: dict[str, list[float]] = {}
            for item in result:
                value = item.get(field)
                group = str(item.get(group_by) or "")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    groups.setdefault(group, []).append(float(value))
            result = [
                {group_by: group, field: sum(values), "count": len(values)}
                for group, values in groups.items()
            ]
        elif op == "spatial_filter":
            result, error = _spatial_filter(result, operation)
            if error is not None:
                return result, error
    return result, None


###############################################################################
def _matches(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return actual == expected
    if operator == "neq":
        return actual != expected
    if operator == "in":
        return is_json_array(expected) and actual in expected
    if operator == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        return is_json_array(actual) and expected in actual
    if operator == "gte":
        return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual >= expected
    return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual <= expected


###############################################################################
def _spatial_filter(
    records: list[dict[str, Any]], operation: dict[str, Any]
) -> tuple[list[dict[str, Any]], str | None]:
    field = str(operation.get("field") or "geometry")
    center = operation.get("center")
    radius_km = operation.get("radius_km")
    if (
        not is_json_array(center)
        or len(center) != 2
        or not isinstance(radius_km, (int, float))
        or isinstance(radius_km, bool)
        or radius_km <= 0
    ):
        return records, "spatial_filter requires center and positive radius_km."
    try:
        lon0, lat0 = float(center[0]), float(center[1])
        radius_value = float(radius_km)
    except (TypeError, ValueError):
        return records, "spatial_filter requires numeric center and radius."
    if not -180 <= lon0 <= 180 or not -90 <= lat0 <= 90:
        return records, "spatial_filter center is outside coordinate bounds."

    def within(item: dict[str, Any]) -> bool:
        geometry = item.get(field)
        coordinates = geometry.get("coordinates") if is_json_object(geometry) else geometry
        if not is_json_array(coordinates) or len(coordinates) < 2:
            return False
        try:
            lon, lat = float(coordinates[0]), float(coordinates[1])
        except (TypeError, ValueError):
            return False
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            return False
        dlat = math.radians(lat - lat0)
        dlon = math.radians(lon - lon0)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat0)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
        distance = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
        return distance <= radius_value

    return [item for item in records if within(item)], None


###############################################################################
def _failure(
    *, tool_name: str, code: str, message: str, recovery: str, started: float
) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name=tool_name,
        status="failed",
        summary=message,
        error=ToolExecutionError(
            error_type=(
                "state_conflict"
                if code in {"unknown_evidence", "failed_evidence"}
                else "semantic_validation"
            ),
            code=code,
            message=message,
            retryable=False,
            recovery=recovery,  # type: ignore[arg-type]
        ),
        metadata=ToolExecutionMetadata(
            duration_ms=max(0, int((time.perf_counter() - started) * 1000))
        ),
    )


__all__ = ["EvidenceToolHandler"]
