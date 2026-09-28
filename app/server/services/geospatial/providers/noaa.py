from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlencode, urlsplit

from server.common.typing import is_json_array, is_json_object, json_array, json_object

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderError,
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

    ALERT_ZONE_CACHE_TTL_SECONDS = 86_400
    ALERT_ZONE_CACHE_STALE_SECONDS = 86_400
    MAX_ALERT_ZONE_LOOKUPS = 32

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
            zone_geometries, zone_warnings = await self._load_alert_zone_geometries(
                payload
            )
            features = _normalize_noaa_alerts(
                payload,
                zone_geometries=zone_geometries,
            )
            unresolved_geometry_count = sum(
                1
                for feature in features
                if not _valid_noaa_geometry(feature.get("geometry"))
            )
            warnings = list(zone_warnings)
            if unresolved_geometry_count:
                warnings.append(
                    f"{unresolved_geometry_count} NOAA alert(s) did not include a "
                    "usable alert or affected-zone boundary and remain data-only."
                )
            partial = bool(warnings)
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
                warnings=warnings,
                result_status=(
                    "valid_empty"
                    if not features
                    else "partial"
                    if partial
                    else "ok"
                ),
                result_type="features",
                partial=partial,
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
    async def _load_alert_zone_geometries(
        self, payload: object
    ) -> tuple[dict[str, dict[str, object]], list[str]]:
        """Resolve missing alert geometries from official NWS forecast zones.

        Some NWS products, including Air Quality Alerts, legitimately omit an
        alert polygon while still declaring their affected forecast zones.
        The zone links are provider-owned URLs, so resolving them server-side
        preserves the alert as data and gives the browser a real GeoJSON
        boundary without trusting model-supplied geometry or external URLs.
        """

        raw_features = (
            payload.get("features")
            if is_json_object(payload)
            else None
        )
        if not is_json_array(raw_features):
            return {}, []

        zone_urls: set[str] = set()
        for raw_feature in raw_features:
            if not is_json_object(raw_feature):
                continue
            if _normalize_noaa_geometry(raw_feature.get("geometry")) is not None:
                continue
            zone_urls.update(
                _noaa_alert_zone_urls(json_object(raw_feature.get("properties")))
            )
        ordered_urls = sorted(zone_urls)
        warnings: list[str] = []
        if len(ordered_urls) > self.MAX_ALERT_ZONE_LOOKUPS:
            warnings.append(
                "NOAA returned more affected zones than the bounded alert "
                f"geometry lookup limit ({self.MAX_ALERT_ZONE_LOOKUPS}); "
                "the remaining zones were not requested."
            )
            ordered_urls = ordered_urls[: self.MAX_ALERT_ZONE_LOOKUPS]

        async def load_zone(
            zone_url: str,
        ) -> tuple[str, dict[str, object] | None, bool]:
            cache_key = f"noaa:alert-zone:v1:{zone_url}"
            cached = self.cache.get(cache_key)
            if cached.status in {CacheLookupStatus.HIT, CacheLookupStatus.STALE}:
                cached_geometry = cached.value
                return (
                    zone_url,
                    cached_geometry if _valid_noaa_geometry(cached_geometry) else None,
                    False,
                )
            try:
                zone_payload = await call_json_fetcher(
                    self.fetcher,
                    zone_url,
                    {"User-Agent": "AEGIS-Geospatial-View/1.0"},
                )
                geometry = _normalize_noaa_zone_geometry(zone_payload)
            except Exception:
                return zone_url, None, True
            if geometry is None:
                return zone_url, None, True
            self.cache.set(
                cache_key,
                geometry,
                ttl_seconds=self.ALERT_ZONE_CACHE_TTL_SECONDS,
                stale_while_revalidate_seconds=self.ALERT_ZONE_CACHE_STALE_SECONDS,
            )
            return zone_url, geometry, False

        results = await asyncio.gather(*(load_zone(url) for url in ordered_urls))
        geometries: dict[str, dict[str, object]] = {}
        failures = 0
        for zone_url, geometry, failed in results:
            if geometry is not None:
                geometries[zone_url] = geometry
            if failed:
                failures += 1
        if failures:
            warnings.append(
                f"NOAA affected-zone geometry lookup failed for {failures} "
                "official zone(s); the alert result may be partially renderable."
            )
        return geometries, warnings

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
            observation_url = (
                f"{self.COOPS_DATA_URL}?{urlencode({**query, 'station': station_id})}"
            )
            payload = await call_json_fetcher(
                self.fetcher,
                observation_url,
                {"User-Agent": "AEGIS-Geospatial-View/1.0"},
            )
            feature = _normalize_coops_observation(payload, station, query)
            if feature is None:
                warnings.append(
                    f"NOAA station '{station_id}' returned no current water level."
                )
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
        except ProviderError:
            if cached.status == CacheLookupStatus.STALE and is_json_array(cached.value):
                return (
                    [json_object(item) for item in json_array(cached.value)],
                    True,
                    [
                        "NOAA station metadata refresh failed; using stale station metadata."
                    ],
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
            if _station_in_bbox(
                station,
                west=west,
                south=south,
                east=east,
                north=north,
            )
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
        raise ProviderMalformedPayloadError(
            "NOAA CO-OPS observation must be an object."
        )
    if payload.get("error"):
        raise ProviderUnavailableError("NOAA CO-OPS rejected the observation request.")
    raw_data = payload.get("data")
    if not is_json_array(raw_data):
        raise ProviderMalformedPayloadError(
            "NOAA CO-OPS observation is missing a data array."
        )
    for raw_item in reversed(json_array(raw_data)):
        item = json_object(raw_item)
        value = _float_or_none(
            item.get("v") if item.get("v") is not None else item.get("value")
        )
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
    if not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

###############################################################################
def _station_in_bbox(
    station: dict[str, object],
    *,
    west: float,
    south: float,
    east: float,
    north: float,
) -> bool:
    latitude = station.get("latitude")
    longitude = station.get("longitude")
    if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
        return False
    return south <= latitude <= north and west <= longitude <= east

###############################################################################
def _normalize_noaa_alerts(
    payload: object,
    *,
    zone_geometries: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
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
        geometry_source = "alert"
        geometry = _normalize_noaa_geometry(item.get("geometry"))
        zone_urls = _noaa_alert_zone_urls(properties)
        if geometry is None and zone_geometries:
            geometry = _combine_noaa_geometries(
                [
                    zone_geometries[zone_url]
                    for zone_url in zone_urls
                    if zone_url in zone_geometries
                ]
            )
            if geometry is not None:
                geometry_source = "affected_zones"
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
                    "geometrySource": geometry_source,
                    "affectedZoneCount": len(zone_urls),
                },
            }
        )
    return features


###############################################################################
def _noaa_alert_zone_urls(properties: dict[str, object]) -> list[str]:
    """Return only canonical NWS forecast-zone URLs from an alert."""

    candidates: list[object] = []
    affected_zones = properties.get("affectedZones")
    if is_json_array(affected_zones):
        candidates.extend(affected_zones)
    geocode = json_object(properties.get("geocode"))
    ugc = geocode.get("UGC")
    if is_json_array(ugc):
        candidates.extend(
            f"https://api.weather.gov/zones/forecast/{zone_id}"
            for zone_id in ugc
            if isinstance(zone_id, str)
        )

    urls: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        parsed = urlsplit(candidate.strip())
        if (
            parsed.scheme.casefold() != "https"
            or parsed.netloc.casefold() != "api.weather.gov"
            or not parsed.path.casefold().startswith("/zones/forecast/")
        ):
            continue
        zone_id = parsed.path.rsplit("/", 1)[-1].strip().upper()
        if len(zone_id) != 6 or not zone_id[:3].isalpha() or not zone_id[3:].isdigit():
            continue
        urls.append(f"https://api.weather.gov/zones/forecast/{zone_id}")
    return list(dict.fromkeys(urls))


###############################################################################
def _normalize_noaa_zone_geometry(payload: object) -> dict[str, object] | None:
    if not is_json_object(payload):
        return None
    return _normalize_noaa_geometry(payload.get("geometry"))


###############################################################################
def _normalize_noaa_geometry(value: object) -> dict[str, object] | None:
    geometry = json_object(value)
    return geometry if _valid_noaa_geometry(geometry) else None


###############################################################################
def _combine_noaa_geometries(
    geometries: list[dict[str, object]],
) -> dict[str, object] | None:
    usable = [geometry for geometry in geometries if _valid_noaa_geometry(geometry)]
    if not usable:
        return None
    if len(usable) == 1:
        return usable[0]
    return {"type": "GeometryCollection", "geometries": usable}


###############################################################################
def _valid_noaa_geometry(value: object) -> bool:
    geometry = json_object(value)
    geometry_type = geometry.get("type")
    if geometry_type == "GeometryCollection":
        geometries = geometry.get("geometries")
        return is_json_array(geometries) and bool(geometries) and all(
            _valid_noaa_geometry(item) for item in geometries
        )
    if geometry_type not in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    }:
        return False
    coordinates = geometry.get("coordinates")
    return is_json_array(coordinates) and bool(coordinates)
