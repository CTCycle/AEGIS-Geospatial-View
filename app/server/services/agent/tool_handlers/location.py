"""Native-v2 location resolution handler."""

from __future__ import annotations

import time
import re

from server.contracts.extraction import LocationSignal
from server.domain.agent.decision import ClarificationRequest, ResolvedLocation
from server.domain.agent.capability_route import AgentState
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.tool_definitions import ResolveLocationInput


_LOCATION_TYPES = frozenset(
    {
        "address",
        "airport",
        "city",
        "country",
        "feature",
        "landmark",
        "poi",
        "region",
        "river",
        "road",
        "street",
        "station",
        "neighborhood",
        "district",
        "municipality",
        "county",
        "province",
        "state",
    }
)

_COORDINATE_PAIR_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*[,;\s]\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$"
)


class LocationToolHandler:
    def __init__(self, *, resolver: LocationResolver) -> None:
        self.resolver = resolver

    async def resolve(
        self,
        request: ResolveLocationInput,
        state: AgentState,
    ) -> ToolResult:
        started = time.perf_counter()
        target_key = _target_key(request)
        if request.query is None and request.target_id in state.location_refs:
            location = state.location_refs[request.target_id]
            return _success(
                location=location,
                target_key=target_key,
                started=started,
            )
        query = (request.query or "").strip()
        if not query:
            return _failure(
                code="unknown_location_target",
                message="The requested location target is not in the current state.",
                recovery="request_user_input",
                started=started,
            )

        coordinates = _parse_coordinate_pair(query)
        if coordinates is not None:
            latitude, longitude = coordinates
            signal = LocationSignal(
                signal_type="coordinates",
                raw_value=query,
                normalized_value=query,
                latitude=latitude,
                longitude=longitude,
                confidence=1.0,
                source="model",
            )
        else:
            expected_type = str(request.expected_location_type or "city").casefold()
            signal_type = expected_type if expected_type in _LOCATION_TYPES else "city"
            signal = LocationSignal(
                signal_type=signal_type,  # type: ignore[arg-type]
                raw_value=query,
                normalized_value=query,
                confidence=1.0,
                source="model",
            )
        memory_snapshot = _memory_snapshot(state)
        result = await self.resolver.resolve_location_signals(
            [signal], memory_snapshot
        )
        if isinstance(result, ClarificationRequest):
            return _failure(
                code="clarification_required",
                message=result.question,
                recovery="request_user_input",
                started=started,
            )
        state.location_refs[target_key] = result
        return _success(location=result, target_key=target_key, started=started)


def _target_key(request: ResolveLocationInput) -> str:
    value = request.target_id or request.candidate_id or request.query or "location"
    return " ".join(value.casefold().split())


def _parse_coordinate_pair(query: str) -> tuple[float, float] | None:
    match = _COORDINATE_PAIR_RE.fullmatch(query)
    if match is None:
        return None
    latitude, longitude = (float(value) for value in match.groups())
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def _memory_snapshot(state: AgentState) -> dict[str, object]:
    location: ResolvedLocation | None = None
    if state.active_map_session is not None:
        location = state.active_map_session.resolved_location
    if location is None and state.location_refs:
        location = next(iter(state.location_refs.values()))
    return {
        "active_location": location.model_dump(mode="json") if location else None
    }


def _success(
    *, location: ResolvedLocation, target_key: str, started: float
) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="resolve_geospatial_location",
        status="success",
        summary=f"Resolved {location.label}.",
        data={
            "target_id": target_key,
            "label": location.label,
            "coordinates": [location.longitude, location.latitude],
            "location_type": location.location_type,
            "bbox": location.bbox,
            "confidence": location.confidence,
        },
        metadata=ToolExecutionMetadata(
            duration_ms=max(0, int((time.perf_counter() - started) * 1000))
        ),
    )


def _failure(
    *, code: str, message: str, recovery: str, started: float
) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="resolve_geospatial_location",
        status="failed",
        summary=message,
        error=ToolExecutionError(
            error_type="state_conflict",
            code=code,
            message=message,
            retryable=False,
            recovery=recovery,  # type: ignore[arg-type]
        ),
        metadata=ToolExecutionMetadata(
            duration_ms=max(0, int((time.perf_counter() - started) * 1000))
        ),
    )


__all__ = ["LocationToolHandler"]
