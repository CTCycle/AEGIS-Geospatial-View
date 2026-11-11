"""GDACS disaster alerts: event points with alert level and severity.

GDACS reports one representative point per event episode. The point is a
reported event location, not an affected area: features carry
``footprint_basis: reported_point`` so derived analysis never treats it as an
inundation or impact footprint.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from server.common.typing import is_json_array, is_json_object, json_object
from server.services.geospatial.providers.base import (
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import JsonFetcher, call_json_fetcher, fetch_bytes_url

GDACS_EVENTS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
GDACS_ATTRIBUTION = "GDACS, Global Disaster Alert and Coordination System (UN, EC)"
GDACS_RANGE_MAX_DAYS = 366
GDACS_CURRENT_DAYS = 7
# The event list returns pages of 100; a bounded number of pages is read.
GDACS_PAGE_SIZE = 100
GDACS_MAX_PAGES = 10
EVENT_TYPES: dict[str, str] = {
    "earthquake": "EQ", "earthquakes": "EQ", "eq": "EQ",
    "cyclone": "TC", "cyclones": "TC", "tropical cyclone": "TC", "hurricane": "TC", "typhoon": "TC", "tc": "TC",
    "flood": "FL", "floods": "FL", "fl": "FL",
    "volcano": "VO", "volcanoes": "VO", "volcanic eruption": "VO", "vo": "VO",
    "drought": "DR", "droughts": "DR", "dr": "DR",
    "wildfire": "WF", "wildfires": "WF", "forest fire": "WF", "wf": "WF",
}
ALERT_LEVELS = {"green": "Green", "orange": "Orange", "red": "Red"}


###############################################################################
async def fetch_gdacs_json(url: str, headers: dict[str, str] | None = None) -> object:
    # An empty selection may come back without a body.
    body = await fetch_bytes_url(url, headers)
    if not body.strip():
        return {"type": "FeatureCollection", "features": []}
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderMalformedPayloadError("Provider returned malformed JSON.") from exc


###############################################################################
class GDACSProvider:
    provider_id = "gdacs"

    # -------------------------------------------------------------------------
    def __init__(self, *, fetcher: JsonFetcher | None = None) -> None:
        self.fetcher: JsonFetcher = fetcher or fetch_gdacs_json

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        start, end = _time_range(request)
        event_types, alert_levels = _categories(request.params.get("categories"))
        query: dict[str, str] = {
            "eventlist": ";".join(event_types or sorted(set(EVENT_TYPES.values()))),
            "fromDate": start.date().isoformat(),
            "toDate": end.date().isoformat(),
            # Without alertlevel the API silently omits Green alerts.
            "alertlevel": ";".join(alert_levels or list(ALERT_LEVELS.values())),
        }
        url = f"{GDACS_EVENTS_URL}?{urlencode(query)}"
        events: list[dict[str, object]] = []
        truncated = True
        for page in range(1, GDACS_MAX_PAGES + 1):
            batch = normalize_gdacs_events(
                await call_json_fetcher(self.fetcher, f"{url}&{urlencode({'pagenumber': page})}")
            )
            events.extend(batch)
            if len(batch) < GDACS_PAGE_SIZE:
                truncated = False
                break
        features = _within_bbox(_unique(events), request.bbox)
        times = [value for value in (item.get("time") for item in features) if isinstance(value, int)]
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "legend": {"type": "category", "label": "GDACS alert level"},
                "freshnessLabel": f"GDACS events {start.date()} to {end.date()}",
                "features": features,
                "totalResults": len(features),
            },
            attribution=[GDACS_ATTRIBUTION],
            warnings=(
                [f"Result capped at {GDACS_MAX_PAGES * GDACS_PAGE_SIZE} events; narrow the "
                 "period, event types or alert levels for the full list."]
                if truncated else []
            ),
            result_status="ok" if features else "valid_empty",
            result_type="features",
            observation_time=datetime.fromtimestamp(max(times) / 1000, UTC).isoformat() if times else None,
            coverage={
                "type": "bbox" if request.bbox else "global",
                "temporal_scope_satisfied": True,
                "truncated": truncated,
                "footprint_basis": "reported_point",
                "completeness_note": (
                    "GDACS lists events that crossed its alert models; each point is a "
                    "reported event location, not an affected-area footprint."
                ),
            },
            source_url=url,
        )


###############################################################################
def normalize_gdacs_events(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload) or not is_json_array(payload.get("features")):
        raise ProviderMalformedPayloadError("GDACS payload must be a GeoJSON FeatureCollection.")
    features: list[dict[str, object]] = []
    for item in json_object(payload).get("features", []):
        feature = json_object(item)
        coordinates = json_object(feature.get("geometry")).get("coordinates")
        if not is_json_array(coordinates) or len(coordinates) < 2:
            continue
        longitude, latitude = coordinates[0], coordinates[1]
        if not (
            isinstance(latitude, int | float) and isinstance(longitude, int | float)
            and -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0
        ):
            continue
        properties = json_object(feature.get("properties"))
        severity = json_object(properties.get("severitydata"))
        links = json_object(properties.get("url"))
        event_type = str(properties.get("eventtype") or "")
        event_id = properties.get("eventid")
        features.append({
            "id": f"{event_type}{event_id}-{properties.get('episodeid')}",
            "name": properties.get("name") or properties.get("eventname"),
            "category": event_type,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "alert_level": properties.get("alertlevel"),
            "alert_score": properties.get("alertscore"),
            "severity": severity.get("severity"),
            "severity_text": severity.get("severitytext"),
            "severity_unit": severity.get("severityunit"),
            "country": properties.get("country"),
            "time": _epoch_ms(properties.get("fromdate")),
            "end_time": _epoch_ms(properties.get("todate")),
            "is_current": properties.get("iscurrent"),
            "footprint_basis": "reported_point",
            "url": links.get("report"),
        })
    return features


###############################################################################
def _time_range(request: ProviderRequest) -> tuple[datetime, datetime]:
    end_value = request.params.get("end_time_iso")
    try:
        end = datetime.fromisoformat(str(end_value).replace("Z", "+00:00")) if end_value else datetime.now(UTC)
    except ValueError as exc:
        raise ProviderInvalidQueryError("The end time must be ISO-8601.") from exc
    end = end if end.tzinfo else end.replace(tzinfo=UTC)
    start = request.time or end - timedelta(days=GDACS_CURRENT_DAYS)
    start = start if start.tzinfo else start.replace(tzinfo=UTC)
    if end <= start:
        raise ProviderInvalidQueryError("The end time must follow the start time.")
    if end - start > timedelta(days=GDACS_RANGE_MAX_DAYS):
        raise ProviderInvalidQueryError(f"GDACS ranges are limited to {GDACS_RANGE_MAX_DAYS} days.")
    return start, end


###############################################################################
def _categories(value: object) -> tuple[list[str], list[str]]:
    """Split category arguments into GDACS event-type and alert-level codes."""

    event_types: list[str] = []
    alert_levels: list[str] = []
    for raw in value if is_json_array(value) else []:
        term = str(raw).strip().casefold()
        if term in EVENT_TYPES and EVENT_TYPES[term] not in event_types:
            event_types.append(EVENT_TYPES[term])
        elif term.removesuffix(" alert") in ALERT_LEVELS:
            alert_levels.append(ALERT_LEVELS[term.removesuffix(" alert")])
        else:
            raise ProviderInvalidQueryError(
                f"Unknown GDACS category '{raw}'. Use event types (earthquake, cyclone, "
                "flood, volcano, drought, wildfire) or alert levels (green, orange, red)."
            )
    return event_types, alert_levels


###############################################################################
def _within_bbox(
    features: list[dict[str, object]], bbox: tuple[float, float, float, float] | None
) -> list[dict[str, object]]:
    if bbox is None:
        return features
    west, south, east, north = bbox
    kept: list[dict[str, object]] = []
    for item in features:
        lon, lat = item["longitude"], item["latitude"]
        assert isinstance(lon, float) and isinstance(lat, float)
        inside_lon = west <= lon <= east if west <= east else lon >= west or lon <= east
        if inside_lon and south <= lat <= north:
            kept.append(item)
    return kept


###############################################################################
def _unique(features: list[dict[str, object]]) -> list[dict[str, object]]:
    """Drop events repeated across pages (the list can shift while paging)."""

    seen: set[object] = set()
    unique: list[dict[str, object]] = []
    for item in features:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return unique


###############################################################################
def _epoch_ms(value: object) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp() * 1000)
