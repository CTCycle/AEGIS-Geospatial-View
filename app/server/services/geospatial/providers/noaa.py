from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlencode

from server.common.typing import is_json_array, is_json_object, json_array, json_object

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

###############################################################################
class NOAAProvider(GeospatialProvider):
    provider_id = "noaa"

    COOPS_STATIONS_URL = (
        "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/"
        "stations.json?type=waterlevels"
    )
    COOPS_DATA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        fetcher: JsonFetcher | None = None,
        cache: GeospatialCache | None = None,
        station_cache_ttl_seconds: int = 86_400,
        station_stale_while_revalidate_seconds: int = 86_400,
    ) -> None:
        self.fetcher = fetcher or fetch_json_url
        self.cache = cache or GeospatialCache()
        self.station_cache_ttl_seconds = station_cache_ttl_seconds
        self.station_stale_while_revalidate_seconds = (
            station_stale_while_revalidate_seconds
        )

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.capability_id == "noaa_coops_water_levels":
            return await self._coops_water_levels(request)
        if request.capability_id == "noaa_radar":
            return self._radar_tiles(request)
        return await self._weather_alerts(request)

    # -------------------------------------------------------------------------
    async def _weather_alerts(self, request: ProviderRequest) -> ProviderResponse:
        params: dict[str, str] = {"status": "actual", "message_type": "alert"}
        if request.bbox is not None:
            west, south, east, north = request.bbox
            params["point"] = f"{(south + north) / 2},{(west + east) / 2}"
        features_url = f"https://api.weather.gov/alerts/active?{urlencode(params)}"
        if request.params.get("live"):
            payload = await call_json_fetcher(
                self.fetcher,
                features_url,
                {"User-Agent": "AEGIS-Geospatial-View/1.0"},
            )
            features = _normalize_noaa_alerts(payload)
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "geojson",
                    "features": features,
                    "totalResults": len(features),
                    "format": "geojson",
                    "legend": {"type": "alert-severity", "label": "NWS alert severity"},
                    "freshnessLabel": "NOAA active alerts feed",
                },
                attribution=["NOAA National Weather Service"],
                result_status="valid_empty" if not features else "ok",
                result_type="features",
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "geojson",
                "featuresUrl": features_url,
                "format": "geojson",
                "legend": {"type": "alert-severity", "label": "NWS alert severity"},
                "freshnessLabel": "NOAA active alerts feed",
            },
            attribution=["NOAA National Weather Service"],
            result_type="metadata",
        )

    # -------------------------------------------------------------------------
    def _radar_tiles(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "raster-tile",
                "tileUrl": "https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows?service=WMS&version=1.3.0&request=GetMap&layers=conus_bref_qcd&styles=&format=image/png&transparent=true&width=256&height=256&crs=EPSG:3857&bbox={bbox-epsg-3857}",
                "format": "wms",
                "legend": {"type": "radar-reflectivity", "label": "Radar reflectivity"},
                "freshnessLabel": "NOAA/NCEP radar layer",
            },
            attribution=["NOAA/NCEP nowCOAST"],
            result_type="raster",
        )

    # -------------------------------------------------------------------------
    async def _coops_water_levels(self, request: ProviderRequest) -> ProviderResponse:
        if not request.params.get("live"):
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=self.provider_id,
                payload={
                    "renderingMode": "clustered-points",
                    "status": "server-side-only",
                    "message": "NOAA station discovery and observations are fetched by the server.",
                    "format": "json",
                    "legend": {"type": "water-level", "label": "Observed water level"},
                    "freshnessLabel": "NOAA CO-OPS water-level observations",
                },
                attribution=["NOAA CO-OPS"],
                result_type="metadata",
            )

        stations, station_stale, station_warnings = await self._load_coops_stations()
        selected = _filter_stations(stations, request)
        query = _coops_query(request)
        features: list[dict[str, object]] = []
        warnings = list(station_warnings)
        for station in selected:
            station_id = str(station["id"])
            observation_url = f"{self.COOPS_DATA_URL}?{urlencode({**query, 'station': station_id})}"
            payload = await call_json_fetcher(
                self.fetcher,
                observation_url,
                {"User-Agent": "AEGIS-Geospatial-View/1.0"},
            )
            feature = _normalize_coops_observation(payload, station, query)
            if feature is None:
                warnings.append(f"NOAA station '{station_id}' returned no current water level.")
            else:
                features.append(feature)

        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "clustered-points",
                "features": features,
                "totalResults": len(features),
                "format": "json",
                "stationCount": len(selected),
                "legend": {"type": "water-level", "label": "Observed water level"},
                "freshnessLabel": "NOAA CO-OPS water-level observations",
            },
            attribution=["NOAA CO-OPS"],
            warnings=warnings,
            stale=station_stale,
            result_status="stale"
            if station_stale
            else "valid_empty"
            if not features
            else "ok",
            result_type="features",
        )

    # -------------------------------------------------------------------------
    async def _load_coops_stations(
        self,
    ) -> tuple[list[dict[str, object]], bool, list[str]]:
        cache_key = "noaa:coops:waterlevel-stations:v1"
        cached = self.cache.get(cache_key)
        if cached.status == CacheLookupStatus.HIT and is_json_array(cached.value):
            return [json_object(item) for item in json_array(cached.value)], False, []
        try:
            payload = await call_json_fetcher(
                self.fetcher,
                self.COOPS_STATIONS_URL,
                {"User-Agent": "AEGIS-Geospatial-View/1.0"},
            )
            stations = _normalize_coops_stations(payload)
            self.cache.set(
                cache_key,
                stations,
                ttl_seconds=self.station_cache_ttl_seconds,
                stale_while_revalidate_seconds=self.station_stale_while_revalidate_seconds,
            )
            return stations, False, []
        except (ProviderUnavailableError, ProviderMalformedPayloadError):
            if cached.status == CacheLookupStatus.STALE and is_json_array(cached.value):
                return (
                    [json_object(item) for item in json_array(cached.value)],
                    True,
                    ["NOAA station metadata refresh failed; using stale station metadata."],
                )
            raise

###############################################################################
def _coops_query(request: ProviderRequest) -> dict[str, str]:
    today = datetime.now(UTC).strftime("%Y%m%d")
    return {
        "product": "water_level",
        "begin_date": str(request.params.get("begin_date") or today),
        "end_date": str(request.params.get("end_date") or today),
        "datum": str(request.params.get("datum") or "MLLW"),
        "time_zone": str(request.params.get("time_zone") or "gmt"),
        "units": str(request.params.get("units") or "metric"),
        "format": "json",
        "application": "AEGIS-Geospatial-View",
    }

###############################################################################
def _normalize_coops_stations(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload) or not is_json_array(payload.get("stations")):
        raise ProviderMalformedPayloadError(
            "NOAA CO-OPS station metadata must contain a stations array."
        )
    stations: list[dict[str, object]] = []
    for raw_station in json_array(payload.get("stations")):
        station = json_object(raw_station)
        station_id = str(station.get("id") or "").strip()
        latitude = _float_or_none(
            station.get("lat")
            if station.get("lat") is not None
            else station.get("latitude")
        )
        longitude = _float_or_none(
            station.get("lng")
            if station.get("lng") is not None
            else station.get("lon")
            if station.get("lon") is not None
            else station.get("longitude")
        )
        if not station_id or latitude is None or longitude is None:
            continue
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue
        stations.append(
            {
                "id": station_id,
                "name": station.get("name") or station_id,
                "latitude": latitude,
                "longitude": longitude,
                "state": station.get("state"),
                "timezone": station.get("timezone"),
            }
        )
    return stations

###############################################################################
def _filter_stations(
    stations: list[dict[str, object]], request: ProviderRequest
) -> list[dict[str, object]]:
    filtered = stations
    if request.bbox is not None:
        west, south, east, north = request.bbox
        filtered = [
            station
            for station in stations
            if south <= float(station["latitude"]) <= north
            and west <= float(station["longitude"]) <= east
        ]
    limit = max(1, min(int(request.params.get("station_limit") or 25), 100))
    return filtered[:limit]

###############################################################################
def _normalize_coops_observation(
    payload: object,
    station: dict[str, object],
    query: dict[str, str],
) -> dict[str, object] | None:
    if not is_json_object(payload):
        raise ProviderMalformedPayloadError("NOAA CO-OPS observation must be an object.")
    if payload.get("error"):
        raise ProviderUnavailableError("NOAA CO-OPS rejected the observation request.")
    raw_data = payload.get("data")
    if not is_json_array(raw_data):
        raise ProviderMalformedPayloadError(
            "NOAA CO-OPS observation is missing a data array."
        )
    for raw_item in reversed(json_array(raw_data)):
        item = json_object(raw_item)
        value = _float_or_none(item.get("v") if item.get("v") is not None else item.get("value"))
        timestamp = item.get("t") or item.get("time")
        if value is None or not isinstance(timestamp, str) or not timestamp.strip():
            continue
        return {
            "id": station["id"],
            "name": station["name"],
            "category": "water_level",
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "value": value,
            "timestamp": timestamp,
            "metadata": {
                "unit": "meters" if query["units"] == "metric" else "feet",
                "datum": query["datum"],
                "station": station["id"],
                "state": station.get("state"),
            },
        }
    return None

###############################################################################
def _float_or_none(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None

###############################################################################
def _normalize_noaa_alerts(payload: object) -> list[dict[str, object]]:
    if not is_json_object(payload):
        raise ProviderUnavailableError("NOAA alert payload must be a GeoJSON object.")
    raw_features = payload.get("features")
    if not is_json_array(raw_features):
        raise ProviderUnavailableError("NOAA alert payload is missing features.")
    features: list[dict[str, object]] = []
    for item in raw_features:
        if not is_json_object(item):
            continue
        properties = json_object(item.get("properties"))
        geometry = item.get("geometry") if is_json_object(item.get("geometry")) else None
        features.append(
            {
                "id": str(item.get("id") or properties.get("id") or ""),
                "name": properties.get("event") or properties.get("headline"),
                "category": "weather_alert",
                "severity": properties.get("severity"),
                "certainty": properties.get("certainty"),
                "urgency": properties.get("urgency"),
                "areaDescription": properties.get("areaDesc"),
                "effective": properties.get("effective"),
                "expires": properties.get("expires"),
                "geometry": geometry,
                "metadata": {
                    "sender": properties.get("senderName"),
                    "instruction": properties.get("instruction"),
                    "description": properties.get("description"),
                },
            }
        )
    return features
