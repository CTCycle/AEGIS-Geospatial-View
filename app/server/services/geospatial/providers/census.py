from __future__ import annotations

from server.services.geospatial.providers.arcgis_rest import ArcGISRestProvider
from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


###############################################################################
class CensusProvider(ArcGISRestProvider):
    provider_id = "census"

    TIGERWEB_TRACTS_URL = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/"
        "TIGERweb/Tracts_Blocks/MapServer/8/query"
    )
    TIGERWEB_HYDRO_URL = (
        "https://tigerweb.geo.census.gov/arcgis/rest/services/"
        "TIGERweb/Hydro/MapServer/0/query"
    )

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        service_url = self.TIGERWEB_TRACTS_URL
        if "hydrography" in request.capability_id:
            service_url = self.TIGERWEB_HYDRO_URL
        params = {
            **request.params,
            "service_url": request.params.get("service_url") or service_url,
            "attribution": "U.S. Census Bureau TIGERweb",
        }
        response = await super().fetch(
            ProviderRequest(
                capability_id=request.capability_id,
                bbox=request.bbox,
                zoom=request.zoom,
                time=request.time,
                params=params,
            )
        )
        payload = {
            **response.payload,
            "renderingMode": "choropleth"
            if "demographics" in request.capability_id
            else "geojson",
        }
        if "demographics" in request.capability_id:
            payload.update(
                {
                    "classificationField": "population_density",
                    "joinKey": "GEOID",
                    "vintage": request.params.get("vintage") or "latest",
                    "marginOfErrorFields": [],
                }
            )
        return ProviderResponse(
            capability_id=response.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=response.attribution,
            warnings=response.warnings,
            stale=response.stale,
            fetched_at=response.fetched_at,
        )
