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


def normalize_poi_category(raw_category: str | None) -> str:
    value = _category_key(raw_category)
    return POI_CATEGORY_MAP.get(value, value or "unknown")


def deduplicate_poi_features(features: list[PoiFeature]) -> list[PoiFeature]:
    seen: set[tuple[str, str, float, float]] = set()
    deduplicated: list[PoiFeature] = []
    for feature in features:
        key = (
            (feature.name or "").strip().lower(),
            normalize_poi_category(feature.category),
            round(feature.latitude, 5),
            round(feature.longitude, 5),
        )
        fallback_key = (
            feature.source,
            normalize_poi_category(feature.category),
            round(feature.latitude, 5),
            round(feature.longitude, 5),
        )
        if key in seen or fallback_key in seen:
            continue
        seen.add(key)
        seen.add(fallback_key)
        deduplicated.append(feature)
    return deduplicated


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


def _category_key(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


POI_CATEGORY_MAP = {
    "airport": "airports",
    "airports": "airports",
    "aerodrome": "airports",
    "airfield": "airports",
    "heliport": "airports",
    "seaplane_base": "airports",
    "amenity_charging_station": "ev_charging",
    "attraction": "tourism",
    "beach": "beaches",
    "beaches": "beaches",
    "bicycle_parking": "bike_parking",
    "bike_lane": "trails",
    "bike_lanes": "trails",
    "camp_site": "campsites",
    "campsite": "campsites",
    "campsites": "campsites",
    "charging_station": "ev_charging",
    "clinic": "clinics",
    "clinics": "clinics",
    "drinking_water": "drinking_water",
    "ev": "ev_charging",
    "ev_charging": "ev_charging",
    "fire_station": "fire_stations",
    "fire_stations": "fire_stations",
    "fuel": "fuel",
    "fuel_station": "fuel",
    "fuel_stations": "fuel",
    "gas_station": "fuel",
    "gas_stations": "fuel",
    "heritage": "heritage_sites",
    "heritage_sites": "heritage_sites",
    "hospital": "hospitals",
    "hospitals": "hospitals",
    "museum": "tourism",
    "museums": "tourism",
    "parking": "parking",
    "pharmacy": "pharmacies",
    "pharmacies": "pharmacies",
    "pipeline": "pipelines",
    "pipelines": "pipelines",
    "pipeline_marker": "pipelines",
    "pipeline_station": "pipelines",
    "police": "police",
    "power_line": "power",
    "power_plant": "power",
    "power_substation": "power",
    "port": "ports",
    "ports": "ports",
    "harbour": "ports",
    "harbor": "ports",
    "marina": "ports",
    "power": "power",
    "public_toilets": "public_toilets",
    "rail": "rail",
    "railway": "rail",
    "railway_station": "rail",
    "rail_station": "rail",
    "tram_stop": "transit_stops",
    "restaurant": "restaurants",
    "restaurants": "restaurants",
    "school": "schools",
    "schools": "schools",
    "shelter": "shelters",
    "shelters": "shelters",
    "shop": "shops",
    "shops": "shops",
    "station": "transit_stops",
    "telecom": "telecom",
    "communications_tower": "telecom",
    "communication_tower": "telecom",
    "mobile_phone_mast": "telecom",
    "toilets": "public_toilets",
    "tourism": "tourism",
    "trail": "trails",
    "hiking": "trails",
    "hiking_trail": "trails",
    "route_hiking": "trails",
    "trailhead": "trailheads",
    "trailheads": "trailheads",
    "trails": "trails",
    "transit": "transit_stops",
    "transit_stop": "transit_stops",
    "transit_stops": "transit_stops",
    "viewpoint": "viewpoints",
    "viewpoints": "viewpoints",
}


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
