from __future__ import annotations

from server.services.geospatial.providers._request import request_center
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.pvgis import PVGISError, PVGISService


class PVGISProvider(GeospatialProvider):
    provider_id = "pvgis"

    def __init__(self, *, service: PVGISService | None = None) -> None:
        self.service = service or PVGISService()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        latitude, longitude = request_center(request)
        try:
            payload = await self.service.get_point_estimate(latitude, longitude)
        except (PVGISError, ValueError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        warnings = []
        if payload.get("error"):
            warnings.append(str(payload["error"]))
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "metadata-only",
                "provider": self.provider_id,
                "latitude": payload.get("latitude", latitude),
                "longitude": payload.get("longitude", longitude),
                "yearlyKwhPerKwpEstimate": payload.get(
                    "yearly_kwh_per_kwp_estimate"
                ),
                "raw": payload.get("raw") or {},
            },
            attribution=[
                str(payload.get("attribution") or "PVGIS (European Commission JRC)")
            ],
            warnings=warnings,
        )
