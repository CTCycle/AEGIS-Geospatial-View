from __future__ import annotations

from typing import Any

from server.domain.geographics import CameraFeature, PoiFeature


class NormalizationError(ValueError):
    """Raised when a provider payload cannot be normalized."""


def normalize_poi_feature(
    payload: dict[str, Any],
    *,
    source: str,
    category: str,
) -> PoiFeature:
    latitude = _first_number(payload, "latitude", "lat")
    longitude = _first_number(payload, "longitude", "lon", "lng")
    if latitude is None or longitude is None:
        raise NormalizationError("POI payload must include latitude and longitude.")
    return PoiFeature(
        id=str(payload.get("id") or f"{source}:{latitude:.6f}:{longitude:.6f}"),
        name=_optional_string(payload.get("name")),
        category=category,
        source=source,
        latitude=latitude,
        longitude=longitude,
        address=_optional_string(payload.get("address")),
        opening_hours=_optional_string(payload.get("opening_hours")),
        website=_optional_string(payload.get("website")),
        phone=_optional_string(payload.get("phone")),
        metadata={key: value for key, value in payload.items() if key not in _POI_FIELDS},
    )


def normalize_camera_feature(
    payload: dict[str, Any],
    *,
    provider: str,
    camera_type: str,
) -> CameraFeature:
    latitude = _first_number(payload, "latitude", "lat")
    longitude = _first_number(payload, "longitude", "lon", "lng")
    official_url = _optional_string(payload.get("official_url") or payload.get("url"))
    if latitude is None or longitude is None:
        raise NormalizationError("Camera payload must include latitude and longitude.")
    if official_url is None:
        raise NormalizationError("Camera payload must include an official URL.")
    return CameraFeature(
        id=str(payload.get("id") or f"{provider}:{latitude:.6f}:{longitude:.6f}"),
        name=str(payload.get("name") or "Unnamed camera"),
        provider=provider,
        camera_type=camera_type,
        latitude=latitude,
        longitude=longitude,
        last_update_time=payload.get("last_update_time"),
        preview_image_url=_optional_string(payload.get("preview_image_url")),
        official_url=official_url,
        embed_url=_optional_string(payload.get("embed_url")),
        embedding_allowed=bool(payload.get("embedding_allowed", False)),
        stale=bool(payload.get("stale", False)),
        metadata={
            key: value for key, value in payload.items() if key not in _CAMERA_FIELDS
        },
    )


def _first_number(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


_POI_FIELDS = {
    "id",
    "name",
    "latitude",
    "lat",
    "longitude",
    "lon",
    "lng",
    "address",
    "opening_hours",
    "website",
    "phone",
}

_CAMERA_FIELDS = {
    "id",
    "name",
    "latitude",
    "lat",
    "longitude",
    "lon",
    "lng",
    "official_url",
    "url",
    "preview_image_url",
    "embed_url",
    "embedding_allowed",
    "stale",
    "last_update_time",
}
