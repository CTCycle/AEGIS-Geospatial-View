from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from AEGIS.server.services.geospatial.catalog_data import (
    CATALOG_PROVIDERS,
    build_catalog_basemaps,
    build_catalog_overlays,
)
from AEGIS.server.services.geospatial.openaq import OpenAQService
from AEGIS.server.services.geospatial.pvgis import PVGISService
from AEGIS.server.utils.logger import logger

type JsonDict = dict[str, Any]


class GeospatialCatalogService:
    def __init__(
        self,
        *,
        openaq_service: OpenAQService,
        pvgis_service: PVGISService,
        ttl_seconds: float = 300.0,
    ) -> None:
        self.openaq_service = openaq_service
        self.pvgis_service = pvgis_service
        self.ttl_seconds = max(ttl_seconds, 30.0)
        self._cache: dict[str, tuple[float, JsonDict]] = {}
        self._last_call_by_key: dict[str, float] = {}
        self._min_call_interval_seconds = 0.2

    # -------------------------------------------------------------------------
    def _tomtom_key(self) -> str | None:
        return os.getenv("TOMTOM_API_KEY", "").strip() or None

    # -------------------------------------------------------------------------
    def _geoapify_key(self) -> str | None:
        return os.getenv("GEOAPIFY_API_KEY", "").strip() or None

    # -------------------------------------------------------------------------
    def _cache_get(self, key: str) -> JsonDict | None:
        cached = self._cache.get(key)
        if cached is None:
            return None
        ts, payload = cached
        if time.time() - ts > self.ttl_seconds:
            self._cache.pop(key, None)
            return None
        return payload

    # -------------------------------------------------------------------------
    def _cache_set(self, key: str, value: JsonDict) -> None:
        self._cache[key] = (time.time(), value)

    # -------------------------------------------------------------------------
    def list_catalog(self) -> JsonDict:
        tomtom_key = self._tomtom_key()
        geoapify_key = self._geoapify_key()
        providers = [dict(entry) for entry in CATALOG_PROVIDERS]
        basemaps = build_catalog_basemaps(
            tomtom_key=tomtom_key,
            geoapify_key=geoapify_key,
        )
        overlays = build_catalog_overlays(tomtom_key=tomtom_key)
        return {"providers": providers, "basemaps": basemaps, "overlays": overlays}

    # -------------------------------------------------------------------------
    def resolve_basemap(self, basemap_id: str | None) -> JsonDict:
        catalog = self.list_catalog()
        basemaps = catalog["basemaps"]
        selected = basemap_id or "osm_default"
        for entry in basemaps:
            if entry["id"] == selected:
                if entry.get("requires_key") and not entry.get("tile_url"):
                    break
                return entry
        return basemaps[0]

    # -------------------------------------------------------------------------
    def resolve_overlays(self, overlay_ids: list[str]) -> list[JsonDict]:
        catalog = self.list_catalog()
        overlay_lookup = {item["id"]: item for item in catalog["overlays"]}
        resolved: list[JsonDict] = []
        for overlay_id in overlay_ids:
            item = overlay_lookup.get(overlay_id)
            if item is None:
                continue
            if item.get("requires_key") and not item.get("url"):
                continue
            resolved.append(item)
        return resolved

    # -------------------------------------------------------------------------
    def resolve_compliance_warnings(
        self, basemap: JsonDict, overlays: list[JsonDict]
    ) -> list[str]:
        warnings: list[str] = []
        selected = [basemap, *overlays]
        for item in selected:
            provider = item.get("provider")
            if provider == "openaq":
                warnings.append(
                    "OpenAQ coverage varies by location and data source; validate local availability."
                )
            if provider == "eea":
                warnings.append(
                    "EEA noise datasets are EU/EEA-specific and should be shown only for European AOIs."
                )
            if provider in {"tomtom", "geoapify"}:
                warnings.append(
                    f"{provider.capitalize()} usage is subject to API key quotas and attribution requirements."
                )
        return list(dict.fromkeys(warnings))

    # -------------------------------------------------------------------------
    async def fetch_insights(
        self,
        *,
        latitude: float | None,
        longitude: float | None,
        overlay_ids: list[str],
        radius_m: float,
    ) -> JsonDict:
        if latitude is None or longitude is None:
            return {}
        cache_key = (
            f"{latitude:.5f}:{longitude:.5f}:{radius_m:.0f}:"
            + ",".join(sorted(overlay_ids))
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        insights: JsonDict = {}
        if "openaq_air_quality" in overlay_ids:
            insights["air_quality"] = await self._fetch_openaq_insight(
                latitude=latitude, longitude=longitude, radius_m=radius_m
            )
        if "pvgis_solar" in overlay_ids:
            insights["solar_potential"] = await self._fetch_pvgis_insight(
                latitude=latitude, longitude=longitude
            )

        self._cache_set(cache_key, insights)
        return insights

    # -------------------------------------------------------------------------
    async def _apply_rate_limit(self, key: str) -> None:
        now = time.time()
        previous = self._last_call_by_key.get(key, 0.0)
        delay = self._min_call_interval_seconds - (now - previous)
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_call_by_key[key] = time.time()

    # -------------------------------------------------------------------------
    async def _fetch_openaq_insight(
        self, *, latitude: float, longitude: float, radius_m: float
    ) -> JsonDict:
        try:
            await self._apply_rate_limit("openaq")
            return await self.openaq_service.get_nearby_measurements(
                latitude, longitude, radius_m
            )
        except Exception as exc:
            logger.warning("OpenAQ insight failed: %s", exc)
            return {"error": "OpenAQ data unavailable"}

    # -------------------------------------------------------------------------
    async def _fetch_pvgis_insight(self, *, latitude: float, longitude: float) -> JsonDict:
        try:
            await self._apply_rate_limit("pvgis")
            return await self.pvgis_service.get_point_estimate(latitude, longitude)
        except Exception as exc:
            logger.warning("PVGIS insight failed: %s", exc)
            return {"error": "PVGIS data unavailable"}
