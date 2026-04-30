from __future__ import annotations

import asyncio
import json
import math
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.configurations import get_server_settings


class OverpassServiceError(Exception):
    """Base exception for Overpass failures."""


class OverpassRequestError(OverpassServiceError):
    """Raised when Overpass cannot fulfill a request."""


class OverpassService:
    DEFAULT_AMENITIES = (
        "cafe",
        "restaurant",
        "hospital",
        "pharmacy",
        "school",
        "bus_station",
        "train_station",
        "fuel",
        "supermarket",
    )

    def __init__(
        self,
        *,
        base_url: str | None = None,
        user_agent: str | None = None,
        timeout_s: float | None = None,
        cache_ttl_s: float | None = None,
        min_call_interval_s: float | None = None,
        default_radius_m: float | None = None,
        default_limit: int | None = None,
    ) -> None:
        settings = get_server_settings().overpass
        self.base_url = base_url or settings.base_url
        self.user_agent = user_agent or settings.user_agent
        self.timeout_s = timeout_s if timeout_s is not None else settings.timeout
        self.cache_ttl_s = max(
            cache_ttl_s if cache_ttl_s is not None else settings.cache_ttl_s, 30.0
        )
        self.min_call_interval_s = max(
            min_call_interval_s
            if min_call_interval_s is not None
            else settings.min_call_interval_s,
            0.05,
        )
        self.default_radius_m = max(
            default_radius_m
            if default_radius_m is not None
            else settings.default_radius_m,
            100.0,
        )
        self.default_limit = max(
            1, default_limit if default_limit is not None else settings.default_limit
        )
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._last_request_at = 0.0

    async def get_nearby_poi(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_m: float | None = None,
        amenity_tags: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        resolved_radius_m = max(radius_m or self.default_radius_m, 100.0)
        resolved_limit = max(1, limit or self.default_limit)
        tags = [
            tag.strip()
            for tag in (amenity_tags or list(self.DEFAULT_AMENITIES))
            if tag and tag.strip()
        ]
        if not tags:
            tags = list(self.DEFAULT_AMENITIES)
        payload = await asyncio.to_thread(
            self._query_overpass,
            latitude=latitude,
            longitude=longitude,
            radius_m=resolved_radius_m,
            tags=tags,
            limit=resolved_limit,
        )
        elements = (
            payload.get("elements") if isinstance(payload.get("elements"), list) else []
        )
        points: list[dict[str, Any]] = []
        for raw in elements:
            if not isinstance(raw, dict):
                continue
            tags_payload = raw.get("tags") if isinstance(raw.get("tags"), dict) else {}
            amenity = tags_payload.get("amenity")
            if not amenity:
                continue
            lat = raw.get("lat")
            lon = raw.get("lon")
            if lat is None or lon is None:
                center = (
                    raw.get("center") if isinstance(raw.get("center"), dict) else {}
                )
                lat = center.get("lat")
                lon = center.get("lon")
            try:
                lat_value = float(lat)
                lon_value = float(lon)
            except (TypeError, ValueError):
                continue
            distance_m = self._haversine_distance_m(
                latitude, longitude, lat_value, lon_value
            )
            points.append(
                {
                    "id": str(raw.get("id")),
                    "name": tags_payload.get("name") or f"{amenity.title()}",
                    "amenity": str(amenity),
                    "latitude": lat_value,
                    "longitude": lon_value,
                    "distance_m": round(distance_m, 1),
                }
            )
        points.sort(key=lambda item: float(item.get("distance_m") or 0.0))
        trimmed = points[:resolved_limit]
        return {
            "provider": "overpass",
            "kind": "poi_amenities",
            "latitude": latitude,
            "longitude": longitude,
            "radius_m": resolved_radius_m,
            "total_results": len(trimmed),
            "items": trimmed,
            "resolved_at": datetime.now(UTC).isoformat(),
            "attribution": "© OpenStreetMap contributors (ODbL)",
        }

    def _query_overpass(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_m: float,
        tags: list[str],
        limit: int,
    ) -> dict[str, Any]:
        cache_key = f"{latitude:.5f}:{longitude:.5f}:{radius_m:.0f}:{','.join(sorted(tags))}:{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        self._wait_for_rate_limit_slot()
        filters = "\n".join(
            [
                f'node["amenity"="{tag}"](around:{int(radius_m)},{latitude:.6f},{longitude:.6f});'
                f'\nway["amenity"="{tag}"](around:{int(radius_m)},{latitude:.6f},{longitude:.6f});'
                f'\nrelation["amenity"="{tag}"](around:{int(radius_m)},{latitude:.6f},{longitude:.6f});'
                for tag in tags
            ]
        )
        query = f"[out:json][timeout:25];\n(\n{filters}\n);\nout center {limit};"
        payload = urlencode({"data": query}).encode("utf-8")
        request = Request(
            self.base_url,
            data=payload,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise OverpassRequestError(f"Overpass request failed: {exc}") from exc
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OverpassRequestError("Overpass response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise OverpassRequestError("Overpass response payload is malformed.")
        self._cache_set(cache_key, data)
        return data

    def _cache_get(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                return None
            ts, payload = cached
            if time.time() - ts > self.cache_ttl_s:
                self._cache.pop(cache_key, None)
                return None
            return dict(payload)

    def _cache_set(self, cache_key: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cache[cache_key] = (time.time(), payload)

    def _wait_for_rate_limit_slot(self) -> None:
        with self._lock:
            now = time.time()
            delay = self.min_call_interval_s - (now - self._last_request_at)
        if delay > 0:
            time.sleep(delay)
        with self._lock:
            self._last_request_at = time.time()

    def _haversine_distance_m(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        radius = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(d_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c

