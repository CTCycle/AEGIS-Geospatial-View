from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

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
from server.services.geospatial.providers.http import (
    JsonFetcher,
    call_json_fetcher,
    fetch_json_url,
)

WINDY_WEBCAMS_ENDPOINT = "https://api.windy.com/webcams/api/v3/webcams"
STALE_CAMERA_AFTER = timedelta(hours=24)


class WindyWebcamsProvider(GeospatialProvider):
    provider_id = "windy_webcams"

    def __init__(
        self, *, api_key: str | None = None, fetcher: JsonFetcher | None = None
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.fetcher = fetcher or fetch_json_url
        self._last_response: ProviderResponse | None = None

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if not self.api_key:
            raise ProviderAuthError("Windy Webcams API key is required.")
        raw_cameras = request.params.get("mock_cameras")
        if isinstance(raw_cameras, list):
            response = self._response_from_cameras(request, raw_cameras)
            self._last_response = response
            return response
        if not request.params.get("live"):
            response = self._response_from_cameras(request, [])
            self._last_response = response
            return response
        try:
            payload = await call_json_fetcher(
                self.fetcher,
                _build_windy_webcams_url(request),
                {"x-windy-api-key": self.api_key},
            )
        except Exception:
            if self._last_response is not None:
                return replace(
                    self._last_response,
                    stale=True,
                    warnings=[
                        *self._last_response.warnings,
                        "Windy Webcams request failed; returning stale cached camera metadata.",
                    ],
                )
            raise
        response = self._response_from_cameras(request, _extract_windy_cameras(payload))
        self._last_response = response
        return response

    def _response_from_cameras(
        self, request: ProviderRequest, cameras: list[Any]
    ) -> ProviderResponse:
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


def _build_windy_webcams_url(request: ProviderRequest) -> str:
    params = ["include=images,location,urls,player", "limit=50"]
    if request.bbox is not None:
        west, south, east, north = request.bbox
        params.append(f"bbox={west},{south},{east},{north}")
    camera_type = request.params.get("camera_type")
    if camera_type:
        params.append(f"category={camera_type}")
    return f"{WINDY_WEBCAMS_ENDPOINT}?{'&'.join(params)}"


def _extract_windy_cameras(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("webcams")
    if not isinstance(raw_items, list):
        raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return []
    return [_normalize_windy_camera(item) for item in raw_items if isinstance(item, dict)]


def _normalize_windy_camera(item: dict[str, object]) -> dict[str, object]:
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    images = item.get("images") if isinstance(item.get("images"), dict) else {}
    urls = item.get("urls") if isinstance(item.get("urls"), dict) else {}
    player = item.get("player") if isinstance(item.get("player"), dict) else {}
    official_url = _first_nested_url(urls, ("detail", "web", "provider")) or str(
        item.get("url") or ""
    )
    last_update_time = item.get("lastUpdatedOn") or item.get("last_update_time")
    preview_image_url = _preview_image_url(images)
    embedding_allowed = _embedding_allowed(item, player)
    return {
        "id": item.get("webcamId") or item.get("id"),
        "name": item.get("title") or item.get("name"),
        "latitude": location.get("latitude") or item.get("latitude"),
        "longitude": location.get("longitude") or item.get("longitude"),
        "official_url": official_url,
        "preview_image_url": preview_image_url,
        "embed_url": (
            _first_nested_url(player, ("day", "month", "lifetime"))
            if embedding_allowed
            else None
        ),
        "embedding_allowed": embedding_allowed,
        "last_update_time": last_update_time,
        "stale": bool(item.get("status") == "inactive")
        or _is_stale_timestamp(last_update_time),
        "preview_expired": preview_image_url is None
        and _first_nested_url(images, ("current", "preview", "thumbnail", "daylight"))
        is not None,
        "source_payload": item,
    }


def _first_nested_url(payload: object, keys: tuple[str, ...]) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = value.get("url")
            if isinstance(nested, str) and nested:
                return nested
    return None


def _preview_image_url(images: object) -> str | None:
    if not isinstance(images, dict):
        return None
    for key in ("current", "preview", "thumbnail", "daylight"):
        value = images.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            if _is_expired_timestamp(value.get("expiresAt") or value.get("expires_at")):
                continue
            nested = value.get("url")
            if isinstance(nested, str) and nested:
                return nested
    return None


def _embedding_allowed(item: dict[str, object], player: object) -> bool:
    if item.get("embedding_allowed") is True or item.get("embeddingAllowed") is True:
        return True
    if isinstance(player, dict):
        return player.get("embedding_allowed") is True or player.get(
            "embeddingAllowed"
        ) is True
    return False


def _is_stale_timestamp(value: object) -> bool:
    timestamp = _parse_timestamp(value)
    if timestamp is None:
        return False
    return datetime.now(UTC) - timestamp > STALE_CAMERA_AFTER


def _is_expired_timestamp(value: object) -> bool:
    timestamp = _parse_timestamp(value)
    if timestamp is None:
        return False
    return timestamp <= datetime.now(UTC)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
