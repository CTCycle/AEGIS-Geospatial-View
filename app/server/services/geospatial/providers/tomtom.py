from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlencode

from server.domain.geographics import ProviderCredentialValidationResult
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)


###############################################################################
class TomTomProvider(GeospatialProvider):
    provider_id = "tomtom"
    flow_proxy_template = (
        "/api/geospatial/proxy/tomtom/traffic-flow/{z}/{x}/{y}.png"
    )
    basemap_proxy_template = "/api/geospatial/proxy/tomtom/basic/{z}/{x}/{y}.png"

    # -------------------------------------------------------------------------
    def __init__(
        self, *, api_key: str | None = None, fetcher: JsonFetcher | None = None
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.fetcher = fetcher or fetch_json_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("TomTom API key is required.")
        if "incident" in request.capability_id or request.params.get("incidents"):
            url = _build_incidents_url(request, self.api_key)
            payload = await call_json_fetcher(self.fetcher, url)
            features = _normalize_incidents(payload)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "features": features,
                    "totalResults": len(features),
                    "credentialPolicy": "server-side-only",
                },
                attribution=["TomTom"],
            )
        tile_url = self.flow_proxy_template
        if "basic" in request.capability_id:
            tile_url = self.basemap_proxy_template
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "tileUrl": tile_url,
                "credentialPolicy": "server-side-only",
            },
            attribution=["TomTom"],
        )

    # -------------------------------------------------------------------------
    async def validate_credentials(
        self, credentials: Mapping[str, str]
    ) -> ProviderCredentialValidationResult:
        api_key = credentials.get("api_key", "").strip()
        if not api_key:
            return ProviderCredentialValidationResult(
                provider_id=self.provider_id,
                valid=False,
                status="invalid",
                message="TomTom API key is required.",
            )
        request = ProviderRequest(
            capability_id="tomtom_incidents",
            bbox=(-0.2, 51.45, -0.1, 51.55),
            params={"incidents": True},
        )
        try:
            payload = await call_json_fetcher(
                self.fetcher, _build_incidents_url(request, api_key)
            )
            _normalize_incidents(payload)
        except ProviderAuthError:
            return ProviderCredentialValidationResult(
                provider_id=self.provider_id,
                valid=False,
                status="invalid",
                message="TomTom rejected the supplied API key.",
            )
        except ProviderError:
            return ProviderCredentialValidationResult(
                provider_id=self.provider_id,
                valid=False,
                status="error",
                message="TomTom validation request failed.",
            )
        return ProviderCredentialValidationResult(
            provider_id=self.provider_id,
            valid=True,
            status="valid",
            message="TomTom accepted the supplied API key.",
        )


###############################################################################
def build_tomtom_tile_url(kind: str, z: int, x: int, y: int, api_key: str) -> str:
    if kind == "basic":
        return (
            "https://api.tomtom.com/map/1/tile/basic/main/"
            f"{z}/{x}/{y}.png?key={api_key}"
        )
    return (
        "https://api.tomtom.com/traffic/map/4/tile/flow/"
        f"absolute/relative0/{z}/{x}/{y}.png?key={api_key}"
    )


###############################################################################
def _build_incidents_url(request: ProviderRequest, api_key: str) -> str:
    bbox = request.bbox or (-180.0, -90.0, 180.0, 90.0)
    west, south, east, north = bbox
    params = {
        "key": api_key,
        "bbox": f"{west},{south},{east},{north}",
        "fields": (
            "{incidents{type,geometry{type,coordinates},properties"
            "{id,iconCategory,magnitudeOfDelay,events{description,code},"
            "startTime,endTime,from,to,roadNumbers,length,delay}}}"
        ),
        "language": str(request.params.get("language") or "en-US"),
        "timeValidityFilter": str(request.params.get("timeValidityFilter") or "present"),
    }
    return f"https://api.tomtom.com/traffic/services/5/incidentDetails?{urlencode(params)}"


###############################################################################
def _normalize_incidents(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    raw_incidents = payload.get("incidents")
    if not isinstance(raw_incidents, list):
        return []
    features: list[dict[str, object]] = []
    for incident in raw_incidents:
        if not isinstance(incident, dict):
            continue
        properties = (
            incident.get("properties")
            if isinstance(incident.get("properties"), dict)
            else {}
        )
        coordinate = _representative_coordinate(incident.get("geometry"))
        if coordinate is None:
            continue
        longitude, latitude = coordinate
        events = properties.get("events") if isinstance(properties.get("events"), list) else []
        description = _first_event_description(events)
        features.append(
            {
                "id": str(properties.get("id") or f"tomtom:{latitude:.6f}:{longitude:.6f}"),
                "name": description or "Traffic incident",
                "category": _incident_category(properties.get("iconCategory")),
                "source": "tomtom",
                "latitude": latitude,
                "longitude": longitude,
                "metadata": {
                    "type": incident.get("type"),
                    "iconCategory": properties.get("iconCategory"),
                    "magnitudeOfDelay": properties.get("magnitudeOfDelay"),
                    "startTime": properties.get("startTime"),
                    "endTime": properties.get("endTime"),
                    "from": properties.get("from"),
                    "to": properties.get("to"),
                    "roadNumbers": properties.get("roadNumbers") or [],
                    "length": properties.get("length"),
                    "delay": properties.get("delay"),
                    "events": events,
                },
            }
        )
    return features


###############################################################################
def _representative_coordinate(geometry: object) -> tuple[float, float] | None:
    if not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return None
    point = _first_coordinate_pair(coordinates)
    if point is None:
        return None
    longitude, latitude = point
    if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
        return None
    return float(longitude), float(latitude)


###############################################################################
def _first_coordinate_pair(value: object) -> tuple[object, object] | None:
    if not isinstance(value, list) or not value:
        return None
    if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        return value[0], value[1]
    return _first_coordinate_pair(value[0])


###############################################################################
def _first_event_description(events: list[object]) -> str | None:
    for event in events:
        if isinstance(event, dict) and event.get("description"):
            return str(event["description"])
    return None


###############################################################################
def _incident_category(value: object) -> str:
    category = str(value or "").strip()
    return f"traffic_incident_{category}" if category else "traffic_incident"
