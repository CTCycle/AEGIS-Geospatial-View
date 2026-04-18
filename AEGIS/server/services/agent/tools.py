from __future__ import annotations

from typing import Any

from AEGIS.server.services.geospatial.catalog import GeospatialCatalogService
from AEGIS.server.services.geospatial.nominatim import NominatimService
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator


###############################################################################
class AgentTools:
    def __init__(
        self,
        *,
        nominatim_service: NominatimService,
        catalog_service: GeospatialCatalogService,
        search_orchestrator: LocationSearchOrchestrator,
    ) -> None:
        self.nominatim_service = nominatim_service
        self.catalog_service = catalog_service
        self.search_orchestrator = search_orchestrator

    def describe_tools(self) -> list[dict[str, str]]:
        return [
            {
                "name": "location_to_coordinates",
                "description": "Resolve a human place description into latitude and longitude using Nominatim geocoding.",
            },
            {
                "name": "get_weather_forecast",
                "description": "Fetch weather forecast insight for resolved coordinates.",
            },
            {
                "name": "get_air_quality_forecast",
                "description": "Fetch air-quality forecast insight for resolved coordinates.",
            },
            {
                "name": "get_nearby_poi",
                "description": "Fetch nearby points of interest around resolved coordinates.",
            },
            {
                "name": "map_search",
                "description": "Run an orchestrated geospatial search and produce map layers, basemap selection, and optional insights.",
            },
        ]

    async def geocode_location(
        self,
        *,
        address: str | None,
        city: str | None,
        country_name: str | None,
        country_code: str | None = None,
        expected_location_type: str | None = None,
    ) -> dict[str, Any] | None:
        return await self.nominatim_service.extract_coordinates(
            address=address,
            city=city,
            country_name=country_name,
            country_code=country_code,
            expected_location_type=expected_location_type,
        )

    async def get_weather_forecast(
        self, *, latitude: float, longitude: float
    ) -> dict[str, Any]:
        return await self.catalog_service.get_weather_forecast(
            latitude=latitude, longitude=longitude
        )

    async def get_air_quality_forecast(
        self, *, latitude: float, longitude: float
    ) -> dict[str, Any]:
        return await self.catalog_service.get_air_quality_forecast(
            latitude=latitude, longitude=longitude
        )

    async def get_nearby_poi(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_m: float,
    ) -> dict[str, Any]:
        return await self.catalog_service.get_nearby_poi(
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
        )
