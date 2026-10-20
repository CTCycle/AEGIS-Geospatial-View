"""Native evidence inspection and transformation handlers."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from server.common.typing import is_json_array, is_json_object
from server.domain.agent.capability_route import AgentRunState
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

# Coordinate-only result points that receive a reverse-geocoded nearest place
# name, in result order. Nominatim allows one request per second.
MAX_PLACE_LABELS = 10

PlaceLabeler = Callable[[float, float], Awaitable[str | None]]

###############################################################################
class EvidenceToolHandler:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        repository: AgentEvidenceRepository,
        place_labeler: PlaceLabeler | None = None,
    ) -> None:
        self.repository = repository
        self.place_labeler = place_labeler

    # -------------------------------------------------------------------------
    async def inspect(
        self,
        request: InspectEvidenceInput,
        state: AgentRunState,
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
        state: AgentRunState,
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
        parents: list[dict[str, Any]] = []
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
            if summary.kind == "raster_descriptor":
                return _failure(
                    tool_name="transform_evidence", code="unsupported_evidence_records",
                    message="A raster descriptor has no numeric records to analyze. Retrieve located numeric feature evidence from another capability.",
                    recovery="choose_alternate_tool", started=started,
                )
            if summary.status == "failed":
                return _failure(
                    tool_name="transform_evidence",
                    code="failed_evidence",
                    message="Failed evidence cannot be transformed.",
                    recovery="replan",
                    started=started,
                )
            parents.append({"provider": summary.provenance.get("provider_id") or summary.provenance.get("provider"),
                            **summary.provenance,
                            **{key: summary.summary[key] for key in ("coverage", "units", "observation_time", "value_kind") if key in summary.summary}})
            records.extend(_records_from_payload(_decode_json(raw)))
        transformed, error = _apply_operations(
            records,
            [operation.model_dump(mode="python") for operation in request.operations],
        )
        if error is not None:
            return _failure(
                tool_name="transform_evidence",
                code="invalid_transform",
                message=error,
                recovery="correct_arguments",
                started=started,
            )
        status = "success" if transformed else "valid_empty"
        labelled = await self._label_places(transformed)
        points = [point for item in transformed if (point := _record_point(item)) is not None]
        bbox = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)] if points else None
        value_fields = sorted({key for item in transformed for key, value in _properties(item).items() if _numeric(value) is not None})
        unlocated = sum(_record_point(item) is None for item in records)
        provenance = {"operation_count": len(request.operations), "parents": parents,
                      "coverage": [parent.get("coverage") for parent in parents]}
        if len(parents) == 1:
            provenance.update({key: parents[0][key] for key in ("provider", "provider_id", "coverage", "units", "observation_time", "value_kind") if key in parents[0]})
        evidence = self.repository.create(
            conversation_id=state.conversation_id,
            run_id=state.request_id,
            kind="derived",
            media_type="application/json",
            status="available" if transformed else "valid_empty",
            payload={"features": transformed},
            summary={
                "record_count": len(transformed),
                "parent_count": len(refs),
                "bbox": bbox,
                "located_record_count": len(points),
                "place_labelled_count": labelled,
                "value_fields": value_fields,
                "map_eligibility": "renderable" if points else "not_renderable",
            },
            provenance=provenance,
            parent_evidence_ids=refs,
        )
        evidence_ref = str(evidence.evidence_id)
        state.evidence_refs.append(evidence_ref)
        return ToolResult(
            call_id="handler-call",
            tool_name="transform_evidence",
            status=status,
            summary=f"Created derived evidence with {len(transformed)} records.",
            data={"record_count": len(transformed), "parent_refs": refs,
                  "preview": transformed[:5], "located_record_count": len(points),
                  "unlocated_record_count": unlocated, "place_labelled_count": labelled,
                  "parent_coverage": provenance["coverage"]},
            evidence_refs=[evidence_ref],
            metadata=ToolExecutionMetadata(
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                evidence_refs=[evidence_ref],
            ),
        )

    # -------------------------------------------------------------------------
    async def _label_places(self, records: list[dict[str, Any]]) -> int:
        """Attach nearest place names to the leading coordinate-only points."""
        if self.place_labeler is None:
            return 0
        labelled = 0
        candidates = [item for item in records if _properties(item).get("label_kind") == "coordinates"]
        for item in candidates[:MAX_PLACE_LABELS]:
            point = _record_point(item)
            if point is None:
                continue
            label = await self.place_labeler(point[1], point[0])
            if label:
                properties = _properties(item)
                properties["place_label"] = label
                properties["label_kind"] = "nearest_reverse_geocoded"
                labelled += 1
        return labelled

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
        for key in sorted({key for item in records for key in _properties(item)}):
            values: list[float] = []
            for item in records:
                raw_value = _properties(item).get(key)
                if isinstance(raw_value, (int, float)) and not isinstance(
                    raw_value, bool
                ):
                    values.append(float(raw_value))
            if values:
                statistics[key] = {
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                    "mean": sum(values) / len(values),
                    "argmax": _compact_record(max((item for item in records if _numeric(_properties(item).get(key)) is not None), key=lambda item: float(_properties(item)[key]))),
                    "argmin": _compact_record(min((item for item in records if _numeric(_properties(item).get(key)) is not None), key=lambda item: float(_properties(item)[key]))),
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
        "grid_aggregate",
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
                if _matches(_properties(item).get(field), operator, expected)
            ]
        elif op == "temporal_filter":
            field = str(operation.get("field") or "timestamp")
            try:
                start = _timestamp(operation.get("start"))
                end = _timestamp(operation.get("end"))
            except ValueError:
                return result, "temporal_filter bounds must be ISO times or epoch values."
            if start is None and end is None:
                return result, "temporal_filter requires a start or end bound."
            filtered: list[dict[str, Any]] = []
            for item in result:
                try:
                    value = _timestamp(_properties(item).get(field))
                except ValueError:
                    continue
                if value is not None and (start is None or value >= start) and (end is None or value <= end):
                    filtered.append(item)
            result = filtered
        elif op == "sort":
            field = str(operation.get("field") or "")
            if not field:
                return result, "sort requires a field."
            present = [item for item in result if _properties(item).get(field) is not None]
            missing = [item for item in result if _properties(item).get(field) is None]
            present.sort(key=lambda item: _sort_key(_properties(item).get(field)), reverse=bool(operation.get("descending")))
            result = present + missing
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
            metric = str(operation.get("metric") or "sum")
            field = str(operation.get("field") or "")
            group_by = str(operation.get("group_by") or "")
            if not field or not group_by:
                return result, "aggregate requires field and group_by."
            groups: dict[str, list[float]] = {}
            for item in result:
                value = _numeric(_properties(item).get(field))
                group = str(_properties(item).get(group_by) or "")
                if value is not None or metric == "count":
                    groups.setdefault(group, []).append(value or 0.0)
            result = [
                {group_by: group, field: _aggregate(values, metric), "count": len(values)}
                for group, values in groups.items()
            ]
        elif op == "grid_aggregate":
            result = _grid_aggregate(result, operation)
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
        point = _record_point(item, field=field)
        if point is None:
            return False
        lon, lat = point
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


def _properties(item: dict[str, Any]) -> dict[str, Any]:
    properties = item.get("properties")
    return properties if is_json_object(properties) else item


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _sort_key(value: Any) -> tuple[int, Any]:
    number = _numeric(value)
    return (0, number) if number is not None else (1, str(value))


def _timestamp(value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = _numeric(value)
    if number is not None:
        return number / 1000 if abs(number) >= 100_000_000_000 else number
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()


def _record_point(item: dict[str, Any], *, field: str = "geometry") -> tuple[float, float] | None:
    geometry = item.get(field)
    coordinates = geometry.get("coordinates") if is_json_object(geometry) and geometry.get("type") == "Point" else geometry if is_json_array(geometry) else None
    props = _properties(item)
    if not is_json_array(coordinates) or len(coordinates) < 2:
        coordinates = [props.get("longitude"), props.get("latitude")]
    lon, lat = _numeric(coordinates[0]), _numeric(coordinates[1])
    if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def _compact_record(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in _properties(item).items() if not isinstance(value, (list, dict))}


def _aggregate(values: list[float], metric: str) -> float:
    if metric == "count":
        return float(len(values))
    if metric == "mean":
        return sum(values) / len(values)
    if metric == "max":
        return max(values)
    if metric == "min":
        return min(values)
    return sum(values)


def _grid_aggregate(records: list[dict[str, Any]], operation: dict[str, Any]) -> list[dict[str, Any]]:
    size = float(operation["cell_size_deg"])
    field = operation.get("value_field")
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for item in records:
        point = _record_point(item)
        if point is not None:
            key = (math.floor((point[0] + 180) / size), math.floor((point[1] + 90) / size))
            groups.setdefault(key, []).append(item)
    cells: list[dict[str, Any]] = []
    for (x, y), items in groups.items():
        west, south = x * size - 180, y * size - 90
        east, north = min(180.0, west + size), min(90.0, south + size)
        values = [value for item in items if (value := _numeric(_properties(item).get(field))) is not None] if field else []
        representative = max(items, key=lambda item: _numeric(_properties(item).get(field)) or 0) if field else items[0]
        cells.append({"longitude": (west + east) / 2, "latitude": (south + north) / 2,
                      "cell_bbox": [west, south, east, north], "count": len(items),
                      "sum": sum(values), "mean": sum(values) / len(values) if values else None,
                      "max": max(values) if values else None, "representative": _compact_record(representative)})
    return sorted(cells, key=lambda item: item.get(str(operation.get("order_by") or "count")) or 0, reverse=True)
