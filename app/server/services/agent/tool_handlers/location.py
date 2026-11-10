"""Native location resolution handler."""

from __future__ import annotations

import logging
import time
import re

from pydantic import ValidationError

from server.common.logging_handlers import log_unexpected_failure
from server.common.identifiers import COORDINATE_PAIR_RE, location_ref_matches, parse_coordinate_pair
from server.common.typing import json_object
from server.contracts.geospatial import ClientMapView
from server.contracts.location import LocationSignal
from server.domain.agent.decision import ClarificationRequest, ResolvedLocation
from server.domain.agent.capability_route import AgentRunState, names_data_subject
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.services.agent.location_resolver import NO_CANDIDATE_REASON, LocationResolver
from server.services.agent.tool_definitions import ResolveLocationInput


_LOCATION_TYPES = frozenset(
    {
        "address",
        "airport",
        "city",
        "country",
        "coordinates",
        "administrative_geometry",
        "feature",
        "landmark",
        "poi",
        "region",
    "macro_region",
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

LOGGER = logging.getLogger(__name__)

# An untyped name defaults to a settlement lookup. A landmark match replaces it
# only when it is a different place and clearly more prominent, as for
# "Colosseum" (Rome) against the Queensland locality of the same name.
_LANDMARK_CONFIDENCE_MARGIN = 0.05
_DISTINCT_PLACE_DEGREES = 0.02

# Reserved target for "this area" requests: the viewport the user sees.
_CURRENT_VIEW_NAMES = frozenset({"current map view", "current view"})
CURRENT_VIEW_LABEL = "Current map view"
CURRENT_VIEW_SOURCE = "client_map_view"

_MONTH_BEFORE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s*$",
    re.IGNORECASE,
)
_COORDINATE_PAIR_SEARCH_RE = re.compile(
    r"(?<![\d.])"
    r"(?P<latitude>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"\s*(?:\xB0\s*|degrees?\s*)?(?P<latitude_hemisphere>[NS])?\s*[,;]\s*"
    r"(?P<longitude>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"\s*(?:\xB0\s*|degrees?\s*)?(?P<longitude_hemisphere>[EW])?"
    r"(?![\d])",
    re.IGNORECASE,
)

###############################################################################
class LocationToolHandler:

    # -------------------------------------------------------------------------
    def __init__(self, *, resolver: LocationResolver) -> None:
        self.resolver = resolver

    # -------------------------------------------------------------------------
    async def resolve(
        self,
        request: ResolveLocationInput,
        state: AgentRunState,
    ) -> ToolResult:
        started = time.perf_counter()
        target_key = _target_key(request)
        if request.query is None and request.target_id in state.location_refs:
            location = await self._identified(state, target_key, state.location_refs[request.target_id])
            state.location_refs[request.target_id] = location
            return _success(
                location=location,
                target_key=target_key,
                started=started,
            )
        # The native model may use target_id for the initial route target,
        # before any location reference has been stored. Treat that value as
        # the first resolver query; subsequent calls still use target_id as a
        # state reference through the early return above.
        query = (request.query or request.target_id or "").strip()
        if not query:
            return _failure(
                code="unknown_location_target",
                message="The requested location target is not in the current state.",
                recovery="request_user_input",
                started=started,
            )
        if " ".join(query.casefold().replace("_", " ").split()) in _CURRENT_VIEW_NAMES:
            location = _current_view_location(state)
            if location is None:
                return _failure(
                    code="current_view_unavailable",
                    message=(
                        "The current map view is not available; name the area "
                        "to search instead."
                    ),
                    recovery="request_user_input",
                    started=started,
                )
            state.location_refs[target_key] = location
            return _success(location=location, target_key=target_key, started=started)
        if state.route is not None and names_data_subject(query, state.route):
            return _failure(
                code="not_a_place",
                message=(
                    f'"{query}" names the requested data, not a place. Resolve '
                    "only the place the user named, or World for a global request."
                ),
                recovery="correct_arguments",
                started=started,
            )
        query = _retain_user_stated_location_components(query, state.user_message)

        expected_type = str(request.expected_location_type or "city").casefold()
        if expected_type not in _LOCATION_TYPES:
            return _failure(
                code="invalid_location_type",
                message=(
                    f"Unsupported canonical location type: {expected_type}."
                ),
                recovery="retry_request",
                started=started,
            )

        coordinates = parse_coordinate_pair(query)
        coordinate_source = "model"
        text_coordinate_match = _search_text_coordinates(state.user_message)
        if coordinates is None and text_coordinate_match is not None:
            coordinates = _parse_coordinate_pair_from_text(state.user_message)
            coordinate_source = "text"
        query_coordinate_match = COORDINATE_PAIR_RE.fullmatch(query)
        if coordinates is None:
            invalid_coordinate_text: str | None = None
            if query_coordinate_match is not None:
                invalid_coordinate_text = query
            elif text_coordinate_match is not None:
                invalid_coordinate_text = (
                    text_coordinate_match.group(0).strip().rstrip(".,;")
                )
            if invalid_coordinate_text is not None:
                return _failure(
                    code="invalid_coordinates",
                    message=(
                        f'"{invalid_coordinate_text}" is outside coordinate bounds. '
                        "Latitude must be between -90 and 90, and longitude "
                        "must be between -180 and 180. Provide a valid pair "
                        "or a place name."
                    ),
                    recovery="request_user_input",
                    semantic_outcome="failed",
                    data={
                        "resolution_status": "invalid_coordinates",
                        "query": invalid_coordinate_text,
                        "latitude_bounds": [-90, 90],
                        "longitude_bounds": [-180, 180],
                    },
                    started=started,
                )
        if coordinates is not None:
            latitude, longitude = coordinates
            signal = LocationSignal(
                signal_type="coordinates",
                raw_value=f"{latitude:g}, {longitude:g}",
                normalized_value=f"{latitude:g}, {longitude:g}",
                latitude=latitude,
                longitude=longitude,
                confidence=1.0,
                source=coordinate_source,  # type: ignore[arg-type]
            )
        else:
            signal_type = expected_type
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
        if request.expected_location_type is None and coordinates is None:
            if isinstance(result, ResolvedLocation):
                result = await self._prefer_prominent_landmark(
                    query, result, memory_snapshot, state
                )
            elif result.reason == NO_CANDIDATE_REASON:
                # The untyped default is "city"; a country or region ("Italy")
                # or a named site never matches it. Ambiguities still ask.
                for fallback_type in ("administrative_geometry", "landmark"):
                    retry = await self.resolver.resolve_location_signals(
                        [signal.model_copy(update={"signal_type": fallback_type})],
                        memory_snapshot,
                    )
                    if isinstance(retry, ResolvedLocation):
                        result = retry
                        break
        if isinstance(result, ClarificationRequest):
            return _failure(
                code="clarification_required",
                message=result.question,
                recovery="request_user_input",
                semantic_outcome="ambiguous",
                data={
                    "resolution_status": "ambiguous",
                    "question": result.question,
                    "reason": result.reason,
                    "missing_fields": list(result.missing_fields),
                    "options": list(result.options),
                },
                started=started,
            )
        result = await self._identified(state, target_key, result)
        state.location_refs[target_key] = result
        return _success(location=result, target_key=target_key, started=started)

    # -------------------------------------------------------------------------
    async def _identified(
        self, state: AgentRunState, target_key: str, location: ResolvedLocation
    ) -> ResolvedLocation:
        """Reverse-geocode a coordinate target the request asks to identify.

        Only an identification obligation naming this target (or naming no
        target) asks for the place's name; other coordinates stay bare.
        """

        if location.location_type != "coordinates" or location.reverse_geocoded_name():
            return location
        obligations = state.goal.obligations if state.goal is not None else []
        if not any(
            item.kind == "identification"
            and (
                not item.target_ids
                or any(location_ref_matches(target, target_key, location.label) for target in item.target_ids)
            )
            for item in obligations
        ):
            return location
        return await self.resolver.reverse_geocode(location) or location

    # -------------------------------------------------------------------------
    async def _prefer_prominent_landmark(
        self,
        query: str,
        settlement: ResolvedLocation,
        memory_snapshot: dict[str, object],
        state: AgentRunState,
    ) -> ResolvedLocation:
        signal = LocationSignal(
            signal_type="landmark",
            raw_value=query,
            normalized_value=query,
            confidence=1.0,
            source="model",
        )
        try:
            landmark = await self.resolver.resolve_location_signals(
                [signal], memory_snapshot
            )
        except Exception as exc:
            # The settlement already resolved; a failed second look keeps it.
            log_unexpected_failure(
                LOGGER, exc, stage="landmark_lookup", level=logging.WARNING,
                run_id=state.run_id or state.request_id,
            )
            return settlement
        if not isinstance(landmark, ResolvedLocation):
            return settlement
        distance = abs(landmark.latitude - settlement.latitude) + abs(
            landmark.longitude - settlement.longitude
        )
        if (
            distance > _DISTINCT_PLACE_DEGREES
            and landmark.confidence > settlement.confidence + _LANDMARK_CONFIDENCE_MARGIN
        ):
            return landmark
        return settlement

###############################################################################
def _current_view_location(state: AgentRunState) -> ResolvedLocation | None:
    """The client-reported viewport as a bbox location, when one was sent."""

    view = json_object(state.map_memory.get("current_view"))
    if not view:
        return None
    try:
        current = ClientMapView.model_validate(
            {key: value for key, value in view.items() if key != "source"}
        )
    except ValidationError:
        return None
    return ResolvedLocation(
        label=CURRENT_VIEW_LABEL,
        latitude=current.center[1],
        longitude=current.center[0],
        source=CURRENT_VIEW_SOURCE,
        confidence=1.0,
        location_type="viewport",
        bbox=list(current.bounds),
        bbox_source=CURRENT_VIEW_SOURCE,
    )

###############################################################################
def _target_key(request: ResolveLocationInput) -> str:
    value = request.target_id or request.candidate_id or request.query or "location"
    return " ".join(value.casefold().split())

###############################################################################
def _retain_user_stated_location_components(query: str, user_message: str) -> str:
    """Drop model-added parent qualifiers that could conceal place ambiguity."""

    components = [part.strip() for part in query.split(",") if part.strip()]
    if len(components) < 2:
        return query

    def normalized_phrase(value: str) -> str:
        return " ".join(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))

    message = f" {normalized_phrase(user_message)} "
    target = normalized_phrase(components[0])
    if not target or f" {target} " not in message:
        return query

    retained = [components[0]]
    for component in components[1:]:
        qualifier = normalized_phrase(component)
        if qualifier and f" {qualifier} " in message:
            retained.append(component)
    return ", ".join(retained)

###############################################################################
def _search_text_coordinates(text: str) -> re.Match[str] | None:
    """Find a coordinate pair in free text, ignoring calendar dates ("March 7, 2024")."""

    for match in _COORDINATE_PAIR_SEARCH_RE.finditer(text):
        if _MONTH_BEFORE_RE.search(text[: match.start()]) is None:
            return match
    return None

###############################################################################
def _parse_coordinate_pair_from_text(text: str) -> tuple[float, float] | None:
    match = _search_text_coordinates(text)
    if match is None:
        return None
    latitude = float(match.group("latitude"))
    longitude = float(match.group("longitude"))
    latitude_hemisphere = (match.group("latitude_hemisphere") or "").casefold()
    longitude_hemisphere = (match.group("longitude_hemisphere") or "").casefold()
    if latitude_hemisphere == "s":
        latitude = -abs(latitude)
    elif latitude_hemisphere == "n":
        latitude = abs(latitude)
    if longitude_hemisphere == "w":
        longitude = -abs(longitude)
    elif longitude_hemisphere == "e":
        longitude = abs(longitude)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude

###############################################################################
def _memory_snapshot(state: AgentRunState) -> dict[str, object]:
    location: ResolvedLocation | None = None
    if state.active_map_session is not None:
        location = state.active_map_session.resolved_location
    if location is None and state.location_refs:
        location = next(iter(state.location_refs.values()))
    return {
        "active_location": location.model_dump(mode="json") if location else None
    }

###############################################################################
def _success(
    *, location: ResolvedLocation, target_key: str, started: float
) -> ToolResult:
    place = location.reverse_geocoded_name()
    return ToolResult(
        call_id="handler-call",
        tool_name="resolve_geospatial_location",
        status="success",
        summary=f"Resolved {location.label}" + (f": {place}." if place else "."),
        data={
            "target_id": target_key,
            "label": location.label,
            **({"place": place} if place else {}),
            "coordinates": [location.longitude, location.latitude],
            "location_type": location.location_type,
            "bbox": location.bbox,
            "confidence": location.confidence,
        },
        semantic_outcome="resolved",
        metadata=ToolExecutionMetadata(
            duration_ms=max(0, int((time.perf_counter() - started) * 1000))
        ),
    )

###############################################################################
def _failure(
    *,
    code: str,
    message: str,
    recovery: str,
    started: float,
    semantic_outcome: str = "not_found",
    data: dict[str, object] | None = None,
) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="resolve_geospatial_location",
        status="failed",
        summary=message,
        semantic_outcome=semantic_outcome,  # type: ignore[arg-type]
        data=data,
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
