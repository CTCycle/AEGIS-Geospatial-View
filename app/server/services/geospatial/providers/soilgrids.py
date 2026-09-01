from __future__ import annotations

from urllib.parse import urlencode

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)

SOILGRIDS_BASE_URL = "https://maps.isric.org/mapserv"
SOILGRIDS_PROPERTIES: dict[str, dict[str, object]] = {
    "bdod": {"label": "Bulk density", "unit": "cg/cm3", "conversion_factor": 100},
    "cec": {"label": "Cation exchange capacity at pH 7", "unit": "mmol(c)/kg", "conversion_factor": 10},
    "cfvo": {"label": "Coarse fragments", "unit": "cm3/dm3", "conversion_factor": 10},
    "clay": {"label": "Clay", "unit": "g/kg", "conversion_factor": 10},
    "nitrogen": {"label": "Total nitrogen", "unit": "cg/kg", "conversion_factor": 100},
    "ocd": {"label": "Organic carbon density", "unit": "hg/m3", "conversion_factor": 10},
    "ocs": {"label": "Organic carbon stock", "unit": "t/ha", "conversion_factor": 10},
    "soc": {"label": "Soil organic carbon", "unit": "dg/kg", "conversion_factor": 10},
    "phh2o": {"label": "Soil pH in water", "unit": "pH x 10", "conversion_factor": 10},
    "sand": {"label": "Sand", "unit": "g/kg", "conversion_factor": 10},
    "silt": {"label": "Silt", "unit": "g/kg", "conversion_factor": 10},
    "wv0010": {"label": "Volumetric water content at 10 kPa", "unit": "1e-3 cm3/cm3", "conversion_factor": 10},
    "wv1500": {"label": "Volumetric water content at 1500 kPa", "unit": "1e-3 cm3/cm3", "conversion_factor": 10},
    "wv003": {"label": "Volumetric water content at 33 kPa", "unit": "1e-3 cm3/cm3", "conversion_factor": 10},
}
SOILGRIDS_DEPTHS = {
    "0-5cm",
    "5-15cm",
    "15-30cm",
    "30-60cm",
    "60-100cm",
    "100-200cm",
}
SOILGRIDS_QUANTILES = {"mean", "Q0.05", "Q0.5", "Q0.50", "Q0.95"}


###############################################################################
class SoilGridsProvider(GeospatialProvider):
    provider_id = "soilgrids"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        property_id = str(request.params.get("property") or "phh2o").strip().lower()
        depth = str(request.params.get("depth") or "0-5cm").strip()
        quantile = str(request.params.get("quantile") or "mean").strip()

        if property_id not in SOILGRIDS_PROPERTIES:
            raise ProviderUnavailableError(
                f"Unsupported SoilGrids property '{property_id}'."
            )
        if depth not in SOILGRIDS_DEPTHS:
            raise ProviderUnavailableError(f"Unsupported SoilGrids depth '{depth}'.")
        if quantile not in SOILGRIDS_QUANTILES:
            raise ProviderUnavailableError(
                f"Unsupported SoilGrids quantile '{quantile}'."
            )

        coverage_id = f"{property_id}_{depth}_{quantile}"
        service_url = f"{SOILGRIDS_BASE_URL}?map=/map/{property_id}.map"
        wms_query = urlencode(
            {
                "SERVICE": "WMS",
                "VERSION": "1.1.1",
                "REQUEST": "GetMap",
                "LAYERS": coverage_id,
                "STYLES": "",
                "FORMAT": "image/png",
                "TRANSPARENT": "TRUE",
                "SRS": "EPSG:3857",
                "WIDTH": "256",
                "HEIGHT": "256",
            }
        )
        tile_url = f"{service_url}&{wms_query}&BBOX={{bbox-epsg-3857}}"
        wcs_capabilities_url = (
            f"{service_url}&SERVICE=WCS&VERSION=2.0.0&REQUEST=GetCapabilities"
        )
        describe_coverage_url = (
            f"{service_url}&SERVICE=WCS&VERSION=2.0.0&REQUEST=DescribeCoverage"
            f"&COVERAGEID={coverage_id}"
        )
        property_metadata = SOILGRIDS_PROPERTIES[property_id]

        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "wms",
                "tileUrl": tile_url,
                "serviceUrl": service_url,
                "layer": coverage_id,
                "coverageId": coverage_id,
                "property": property_id,
                "propertyLabel": property_metadata["label"],
                "depth": depth,
                "quantile": quantile,
                "mappedUnit": property_metadata["unit"],
                "conversionFactor": property_metadata["conversion_factor"],
                "wcsCapabilitiesUrl": wcs_capabilities_url,
                "describeCoverageUrl": describe_coverage_url,
                "availableProperties": sorted(SOILGRIDS_PROPERTIES),
                "availableDepths": sorted(SOILGRIDS_DEPTHS),
                "availableQuantiles": ["mean", "Q0.05", "Q0.5", "Q0.95"],
                "legend": {
                    "type": "soil-property",
                    "label": f"{property_metadata['label']} ({depth}, {quantile})",
                },
                "freshnessLabel": "ISRIC SoilGrids rolling global release",
                "spatialResolution": "250 m",
                "warning": (
                    "SoilGrids values are model predictions at 250 m resolution and "
                    "should not be treated as parcel-scale soil measurements."
                ),
            },
            attribution=["ISRIC - World Soil Information, SoilGrids"],
            result_type="raster",
        )
