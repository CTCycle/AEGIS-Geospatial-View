from __future__ import annotations

from server.services.geospatial.normalizers import (
    NormalizationError,
    normalize_camera_feature,
)
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderRequest,
    ProviderResponse,
)


class WindyWebcamsProvider(GeospatialProvider):
    provider_id = "windy_webcams"

    def __init__(self, *, api_key: str | None = None) -> None:
        self.api_key = (api_key or "").strip()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("Windy Webcams API key is required.")
        raw_cameras = request.params.get("mock_cameras")
        cameras = raw_cameras if isinstance(raw_cameras, list) else []
        features = []
        for item in cameras:
            if not isinstance(item, dict):
                continue
            try:
                features.append(
                    normalize_camera_feature(
                        item,
                        provider=self.provider_id,
                        camera_type=str(item.get("camera_type") or "webcam"),
                    ).model_dump(mode="json")
                )
            except NormalizationError:
                continue
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "camera-points",
                "features": features,
                "totalResults": len(features),
                "previewRefreshRequired": True,
                "embeddingPolicy": "official-link-only-unless-explicitly-allowed",
            },
            attribution=["Windy Webcams"],
        )
