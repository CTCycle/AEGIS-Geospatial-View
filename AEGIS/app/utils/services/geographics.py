from __future__ import annotations

import math
from datetime import date
from typing import Final
from urllib.parse import urlencode

import httpx

from AEGIS.app.api.schemas.gibs import (
    GIBSImageryPayload,
    GIBSLayerConfiguration,
    GIBSRequest,
    GIBSTileCoordinates,
    ResolvedLocation,
    TemporalParameters,
)
from AEGIS.app.api.schemas.geographics import MapRequest
from AEGIS.app.logger import logger


GIBS_BASE_URL: Final[str] = "https://gibs.earthdata.nasa.gov"
DEFAULT_LAYER_KEY: Final[str] = "natural color"
QUALITY_SEGMENT: Final[str] = "best"
SERVICE_SEGMENT: Final[str] = "wmts"
DEFAULT_PROJECTION: Final[str] = "epsg3857"
MAX_LATITUDE: Final[float] = 85.051128
IMAGERY_TIMEOUT_SECONDS: Final[float] = 20.0

COUNTRY_PRESETS: Final[dict[str, tuple[float, float]]] = {
    "italy": (41.8719, 12.5674),
    "united states": (39.8283, -98.5795),
    "united kingdom": (55.3781, -3.4360),
    "canada": (56.1304, -106.3468),
    "australia": (-25.2744, 133.7751),
}

CITY_PRESETS: Final[dict[str, tuple[float, float]]] = {
    "rome": (41.9028, 12.4964),
    "milan": (45.4642, 9.19),
    "naples": (40.8518, 14.2681),
    "new york": (40.7128, -74.006),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "london": (51.5074, -0.1278),
    "manchester": (53.4808, -2.2426),
    "toronto": (43.6532, -79.3832),
    "vancouver": (49.2827, -123.1207),
    "sydney": (-33.8688, 151.2093),
    "melbourne": (-37.8136, 144.9631),
    "brisbane": (-27.4698, 153.0251),
    "ottawa": (45.4215, -75.6972),
    "montreal": (45.5017, -73.5673),
}

LAYER_CONFIGS: Final[dict[str, GIBSLayerConfiguration]] = {
    "natural color": GIBSLayerConfiguration(
        filter_key="Natural Color",
        layer_identifier="MODIS_Terra_CorrectedReflectance_TrueColor",
        tile_matrix_set="GoogleMapsCompatible_Level8",
        image_format="jpg",
        mime_type="image/jpeg",
        projection=DEFAULT_PROJECTION,
        min_zoom=0,
        max_zoom=8,
        default_zoom=4,
    ),
    "topographic": GIBSLayerConfiguration(
        filter_key="Topographic",
        layer_identifier="BlueMarble_ShadedRelief_Bathymetry",
        tile_matrix_set="GoogleMapsCompatible_Level8",
        image_format="jpg",
        mime_type="image/jpeg",
        projection=DEFAULT_PROJECTION,
        min_zoom=0,
        max_zoom=8,
        default_zoom=3,
    ),
    "population density": GIBSLayerConfiguration(
        filter_key="Population Density",
        layer_identifier="GPW_Population_Density_2020",
        tile_matrix_set="GoogleMapsCompatible_Level7",
        image_format="png",
        mime_type="image/png",
        projection=DEFAULT_PROJECTION,
        min_zoom=0,
        max_zoom=7,
        default_zoom=3,
    ),
    "weather overlay": GIBSLayerConfiguration(
        filter_key="Weather Overlay",
        layer_identifier="MODIS_Terra_CloudTopPressure_Day",
        tile_matrix_set="GoogleMapsCompatible_Level7",
        image_format="png",
        mime_type="image/png",
        projection=DEFAULT_PROJECTION,
        min_zoom=0,
        max_zoom=7,
        default_zoom=4,
    ),
}


###############################################################################
class GIBSClient:
    def __init__(self) -> None:
        self.layers = LAYER_CONFIGS

    def build_imagery_payload(self, request: MapRequest) -> GIBSImageryPayload:
        layer = self.resolve_layer(request.filter)
        location = self.resolve_location(request)
        zoom_level = self.resolve_zoom(layer)
        tile = self.compute_tile(location.latitude, location.longitude, zoom_level)
        temporal = TemporalParameters(
            reference_date=request.temporal.reference_date,
            time_of_day=request.temporal.time_of_day,
            fallback_year=request.temporal.timeline_year,
        )
        time_value = temporal.iso_value()
        request_payload = self.compose_request(layer, tile, time_value)
        kvp_url = f"{request_payload.kvp_endpoint}?{urlencode(request_payload.kvp_parameters)}"
        caption = self.compose_caption(request, location, tile)
        message = "NASA GIBS imagery request generated successfully."
        logger.debug(
            "GIBS payload generated",
            extra={
                "layer": layer.layer_identifier,
                "time": time_value,
                "tile": {
                    "zoom": tile.zoom,
                    "row": tile.row,
                    "column": tile.column,
                },
                "location": {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "source": location.source,
                },
            },
        )
        return GIBSImageryPayload(
            request=request_payload,
            layer=layer,
            tile=tile,
            location=location,
            caption=caption,
            message=message,
            image_url=request_payload.restful_url,
            kvp_url=kvp_url,
        )

    def resolve_layer(self, filter_name: str | None) -> GIBSLayerConfiguration:
        if not filter_name:
            return self.layers[DEFAULT_LAYER_KEY]
        key = filter_name.strip().lower()
        return self.layers.get(key, self.layers[DEFAULT_LAYER_KEY])

    def resolve_zoom(self, layer: GIBSLayerConfiguration) -> int:
        today = date.today()
        if today.month in {6, 7, 8}:
            candidate = min(layer.max_zoom, layer.default_zoom + 1)
        elif today.month in {12, 1, 2}:
            candidate = max(layer.min_zoom, layer.default_zoom - 1)
        else:
            candidate = layer.default_zoom
        return min(max(candidate, layer.min_zoom), layer.max_zoom)

    def resolve_location(self, request: MapRequest) -> ResolvedLocation:
        if request.mode == "coordinates" and request.coordinates is not None:
            coordinates = request.coordinates
            return ResolvedLocation(
                latitude=coordinates.latitude,
                longitude=coordinates.longitude,
                source="coordinates",
                reference="Coordinates provided by user",
            )

        if request.location is not None:
            location = request.location
            if location.city:
                city_key = location.city.strip().lower()
                if city_key in CITY_PRESETS:
                    latitude, longitude = CITY_PRESETS[city_key]
                    return ResolvedLocation(
                        latitude=latitude,
                        longitude=longitude,
                        source="city",
                        reference=location.city,
                    )
            if location.country:
                country_key = location.country.strip().lower()
                if country_key in COUNTRY_PRESETS:
                    latitude, longitude = COUNTRY_PRESETS[country_key]
                    return ResolvedLocation(
                        latitude=latitude,
                        longitude=longitude,
                        source="country",
                        reference=location.country,
                    )

        raise ValueError(
            "Unable to resolve location. Provide coordinates or choose a supported location."
        )

    def compute_tile(self, latitude: float, longitude: float, zoom: int) -> GIBSTileCoordinates:
        lat_clamped = max(min(latitude, MAX_LATITUDE), -MAX_LATITUDE)
        lon_wrapped = ((longitude + 180.0) % 360.0) - 180.0
        n = 2**zoom
        column = int((lon_wrapped + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat_clamped)
        mercator = math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))
        row = int((1.0 - mercator / math.pi) / 2.0 * n)
        column = min(max(column, 0), n - 1)
        row = min(max(row, 0), n - 1)
        return GIBSTileCoordinates(zoom=zoom, column=column, row=row)

    def compose_request(
        self, layer: GIBSLayerConfiguration, tile: GIBSTileCoordinates, time_value: str
    ) -> GIBSRequest:
        endpoint = self.build_endpoint(layer.projection)
        kvp_endpoint = f"{endpoint}/{SERVICE_SEGMENT}.cgi"
        return GIBSRequest(
            endpoint=endpoint,
            kvp_endpoint=kvp_endpoint,
            layer=layer.layer_identifier,
            time=time_value,
            tile_matrix_set=layer.tile_matrix_set,
            tile_matrix=tile.zoom,
            tile_row=tile.row,
            tile_col=tile.column,
            image_format=layer.image_format,
            mime_type=layer.mime_type,
            projection=layer.projection,
        )

    def build_endpoint(self, projection: str) -> str:
        return f"{GIBS_BASE_URL}/{SERVICE_SEGMENT}/{projection}/{QUALITY_SEGMENT}"

    def compose_caption(
        self, request: MapRequest, location: ResolvedLocation, tile: GIBSTileCoordinates
    ) -> str:
        pieces: list[str] = []
        if request.filter:
            pieces.append(f"Filter: {request.filter}")
        if location.source == "coordinates":
            pieces.append(
                "Coordinates: "
                f"({location.latitude:.4f}, {location.longitude:.4f})"
            )
        else:
            location_parts: list[str] = []
            if request.location is not None:
                if request.location.city:
                    location_parts.append(request.location.city)
                if request.location.country:
                    location_parts.append(request.location.country)
            if location_parts:
                pieces.append("Location: " + ", ".join(location_parts))
            else:
                pieces.append(
                    "Coordinates: "
                    f"({location.latitude:.4f}, {location.longitude:.4f})"
                )
        temporal = request.temporal
        if temporal.reference_date is not None:
            pieces.append(f"Date: {temporal.reference_date.isoformat()}")
        if temporal.time_of_day is not None:
            pieces.append(f"Time: {temporal.time_of_day.strftime('%H:%M:%S')}")
        pieces.append(f"Timeline year: {temporal.timeline_year}")
        pieces.append(f"Tile z/x/y: {tile.zoom}/{tile.column}/{tile.row}")
        return " | ".join(pieces)

    async def download_imagery(self, request: GIBSRequest) -> bytes:
        headers = {"Accept": request.mime_type}
        restful_error: str | None = None
        async with httpx.AsyncClient(timeout=IMAGERY_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(request.restful_url, headers=headers)
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as exc:
                restful_error = self.parse_error_detail(exc.response)
                logger.debug(
                    "GIBS RESTful imagery request failed",
                    extra={
                        "status": exc.response.status_code,
                        "detail": restful_error,
                        "url": request.restful_url,
                    },
                )
            except httpx.RequestError as exc:
                restful_error = str(exc)
                logger.debug(
                    "GIBS RESTful imagery request error",
                    extra={"error": restful_error, "url": request.restful_url},
                )

            try:
                response = await client.get(
                    request.kvp_endpoint,
                    params=request.kvp_parameters,
                    headers=headers,
                )
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as exc:
                detail = self.parse_error_detail(exc.response)
                if restful_error:
                    detail = f"{detail} (RESTful fallback failed: {restful_error})"
                raise ValueError(detail) from exc
            except httpx.RequestError as exc:
                message = f"Unable to reach NASA GIBS service: {exc}"
                if restful_error:
                    message = f"{message} (RESTful fallback failed: {restful_error})"
                raise ValueError(message) from exc

    def parse_error_detail(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            text = response.text.strip()
            return text or f"HTTP {response.status_code}"

        if isinstance(data, dict):
            for key in ("detail", "message", "error", "errors"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        text = response.text.strip()
        if text:
            return text
        return f"HTTP {response.status_code}"

