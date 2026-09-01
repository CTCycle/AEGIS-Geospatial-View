from __future__ import annotations

from urllib.parse import urlencode

from pyproj import Transformer

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)

SOILGRIDS_BASE_URL = "https://maps.isric.org/mapserv"
SOILGRIDS_HOMOLOSINE_CRS = "+proj=igh +datum=WGS84 +units=m +no_defs"
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
    "wv0033": {"label": "Volumetric water content at 33 kPa", "unit": "1e-3 cm3/cm3", "conversion_factor": 10},
}
SOILGRIDS_STANDARD_DEPTHS = {
    "0-5cm",
    "5-15cm",
    "15-30cm",
    "30-60cm",
    "60-100cm",
    "100-200cm",
}
SOILGRIDS_QUANTILES = {"mean", "Q0.05", "Q0.5", "Q0.95"}


###############################################################################
class SoilGridsProvider(GeospatialProvider):
    provider_id = "soilgrids"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        property_id = str(request.params.get("property") or "phh2o").strip().lower()
        depth = str(request.params.get("depth") or "0-5cm").strip()
        quantile = str(request.params.get("quantile") or "mean").strip()
        if quantile == "Q0.50":
            quantile = "Q0.5"

        if property_id not in SOILGRIDS_PROPERTIES:
            raise ProviderUnavailableError(
                f"Unsupported SoilGrids property '{property_id}'."
            )
        allowed_depths = {"0-30cm"} if property_id == "ocs" else SOILGRIDS_STANDARD_DEPTHS
        allowed_quantiles = {"mean"} if property_id == "ocs" else SOILGRIDS_QUANTILES
        if depth not in allowed_depths:
            raise ProviderUnavailableError(
                f"Unsupported SoilGrids depth '{depth}' for property '{property_id}'."
            )
        if quantile not in allowed_quantiles:
            raise ProviderUnavailableError(
                f"Unsupported SoilGrids quantile '{quantile}' for property '{property_id}'."
            )

        coverage_id = f"{property_id}_{depth}_{quantile}"
        service_url = f"{SOILGRIDS_BASE_URL}?map=/map/{property_id}.map"
        wcs_capabilities_url = (
            f"{service_url}&SERVICE=WCS&VERSION=2.0.0&REQUEST=GetCapabilities"
        )
        describe_coverage_url = (
            f"{service_url}&SERVICE=WCS&VERSION=2.0.0&REQUEST=DescribeCoverage"
            f"&COVERAGEID={coverage_id}"
        )
        coverage_download_url = _coverage_download_url(
            service_url=service_url,
            coverage_id=coverage_id,
            bbox=request.bbox,
        )
        property_metadata = SOILGRIDS_PROPERTIES[property_id]

        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "metadata-only",
                "serviceUrl": service_url,
                "coverageId": coverage_id,
                "property": property_id,
                "propertyLabel": property_metadata["label"],
                "depth": depth,
                "quantile": quantile,
                "mappedUnit": property_metadata["unit"],
                "conversionFactor": property_metadata["conversion_factor"],
                "wcsCapabilitiesUrl": wcs_capabilities_url,
                "describeCoverageUrl": describe_coverage_url,
                "coverageDownloadUrl": coverage_download_url,
                "wmsServiceUrl": service_url,
                "availableProperties": sorted(SOILGRIDS_PROPERTIES),
                "availableDepths": sorted(allowed_depths),
                "availableQuantiles": sorted(allowed_quantiles),
                "freshnessLabel": "ISRIC SoilGrids rolling global release",
                "spatialResolution": "250 m",
                "warning": (
                    "SoilGrids values are model predictions at 250 m resolution and "
                    "should not be treated as parcel-scale soil measurements."
                ),
            },
            attribution=["ISRIC - World Soil Information, SoilGrids"],
            result_type="coverage-descriptor",
        )


###############################################################################
def _coverage_download_url(
    *,
    service_url: str,
    coverage_id: str,
    bbox: tuple[float, float, float, float] | None,
) -> str | None:
    if bbox is None:
        return None
    west, south, east, north = bbox
    transformer = Transformer.from_crs(
        "EPSG:4326", SOILGRIDS_HOMOLOSINE_CRS, always_xy=True
    )
    projected = [
        transformer.transform(lon, lat)
        for lon, lat in (
            (west, south),
            (west, north),
            (east, south),
            (east, north),
        )
    ]
    xs = [point[0] for point in projected]
    ys = [point[1] for point in projected]
    query = urlencode(
        [
            ("SERVICE", "WCS"),
            ("VERSION", "2.0.1"),
            ("REQUEST", "GetCoverage"),
            ("COVERAGEID", coverage_id),
            ("FORMAT", "GEOTIFF_INT16"),
            ("SUBSET", f"X({min(xs):.3f},{max(xs):.3f})"),
            ("SUBSET", f"Y({min(ys):.3f},{max(ys):.3f})"),
            (
                "SUBSETTINGCRS",
                "http://www.opengis.net/def/crs/EPSG/0/152160",
            ),
            ("OUTPUTCRS", "http://www.opengis.net/def/crs/EPSG/0/152160"),
        ]
    )
    return f"{service_url}&{query}"
