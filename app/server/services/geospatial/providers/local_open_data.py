from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from server.services.geospatial.providers.base import (
    ProviderMalformedPayloadError,
    ProviderRequest,
    ProviderResponse,
)
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)


class LocalOpenDataProvider:
    provider_id = "local_open_data"

    def __init__(
        self,
        *,
        source_map: dict[str, str] | None = None,
        fetcher: JsonFetcher | None = None,
    ) -> None:
        self.source_map = source_map or self._source_map_from_env()
        self.fetcher = fetcher or fetch_json_url

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        source = str(
            request.params.get("source")
            or request.params.get("source_url")
            or self.source_map.get(request.capability_id)
            or ""
        ).strip()
        if source:
            payload = await self._load_source(source)
        else:
            payload = {
                "renderingMode": "metadata-only",
                "status": "configuration-needed",
                "message": (
                    "Configure a local open-data source URL or file path for this "
                    "capability before rendering live agency data."
                ),
            }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=["Local open data provider"],
        )

    async def fetch_features(self, request: ProviderRequest) -> ProviderResponse:
        return await self.fetch(request)

    async def _load_source(self, source: str) -> dict[str, Any]:
        if source.startswith(("http://", "https://")):
            payload = await call_json_fetcher(self.fetcher, source, None)
        else:
            path = Path(source)
            payload = json.loads(path.read_text(encoding="utf-8"))
        return self._normalize_payload(payload, source=source)

    def _normalize_payload(self, payload: object, *, source: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ProviderMalformedPayloadError("Local open-data source must be a JSON object.")
        if payload.get("type") == "FeatureCollection":
            features = payload.get("features")
            return {
                "renderingMode": "camera-points",
                "type": "FeatureCollection",
                "features": features if isinstance(features, list) else [],
                "source": source,
            }
        cameras = payload.get("cameras")
        if isinstance(cameras, list):
            return {
                "renderingMode": "camera-points",
                "type": "FeatureCollection",
                "features": [self._camera_feature(item) for item in cameras if isinstance(item, dict)],
                "source": source,
            }
        return payload | {"source": source}

    def _camera_feature(self, item: dict[str, Any]) -> dict[str, Any]:
        longitude = item.get("longitude") or item.get("lon")
        latitude = item.get("latitude") or item.get("lat")
        return {
            "type": "Feature",
            "id": item.get("id") or item.get("camera_id") or item.get("name"),
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": item,
        }

    def _source_map_from_env(self) -> dict[str, str]:
        raw = os.getenv("LOCAL_OPEN_DATA_SOURCES", "").strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items() if value}
