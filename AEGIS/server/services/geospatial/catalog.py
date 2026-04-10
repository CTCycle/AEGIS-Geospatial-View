from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
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
        manifest_loader: GeospatialManifestLoader | None = None,
        ttl_seconds: float = 300.0,
    ) -> None:
        self.openaq_service = openaq_service
        self.pvgis_service = pvgis_service
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
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
        manifest = self.manifest_loader.load_all()
        tomtom_key = self._tomtom_key()
        geoapify_key = self._geoapify_key()
        providers = self._map_providers(manifest["providers"])
        basemaps = self._map_basemaps(
            manifest["basemaps"], tomtom_key=tomtom_key, geoapify_key=geoapify_key
        )
        overlays = self._map_overlays(manifest["overlays"], tomtom_key=tomtom_key)
        return {"providers": providers, "basemaps": basemaps, "overlays": overlays}

    # -------------------------------------------------------------------------
    def _map_providers(self, providers: list[JsonDict]) -> list[JsonDict]:
        mapped: list[JsonDict] = []
        for entry in providers:
            metadata = dict(entry.get("metadata") or {})
            mapped.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "docs_url": metadata.get("docs_url", ""),
                    "commercial_notes": metadata.get("commercial_notes", ""),
                    "warning_level": metadata.get("warning_level", "low"),
                }
            )
        return mapped

    # -------------------------------------------------------------------------
    def _map_basemaps(
        self, basemaps: list[JsonDict], *, tomtom_key: str | None, geoapify_key: str | None
    ) -> list[JsonDict]:
        mapped: list[JsonDict] = []
        for entry in basemaps:
            metadata = dict(entry.get("metadata") or {})
            tile_url = metadata.get("tile_url")
            tile_url_template = metadata.get("tile_url_template")
            provider = str(entry.get("provider") or "")
            if not tile_url and isinstance(tile_url_template, str):
                if provider == "tomtom":
                    tile_url = (
                        tile_url_template.replace("{api_key}", tomtom_key)
                        if tomtom_key
                        else None
                    )
                elif provider == "geoapify":
                    tile_url = (
                        tile_url_template.replace("{api_key}", geoapify_key)
                        if geoapify_key
                        else None
                    )
            requires_key = bool(metadata.get("requires_key", False))
            is_available = not requires_key or bool(tile_url)
            availability_reason = None
            if requires_key and not is_available:
                availability_reason = f"{provider.capitalize()} API key is not configured."
            mapped.append(
                {
                    "id": entry["id"],
                    "label": metadata.get("label", entry["name"]),
                    "provider": entry["provider"],
                    "type": entry["type"],
                    "tile_url": tile_url,
                    "attribution": metadata.get("attribution"),
                    "requires_key": requires_key,
                    "is_available": is_available,
                    "availability_reason": availability_reason,
                }
            )
        return mapped

    # -------------------------------------------------------------------------
    def _map_overlays(self, overlays: list[JsonDict], *, tomtom_key: str | None) -> list[JsonDict]:
        mapped: list[JsonDict] = []
        for entry in overlays:
            metadata = dict(entry.get("metadata") or {})
            overlay = {
                "id": entry["id"],
                "label": metadata.get("label", entry["name"]),
                "provider": entry["provider"],
                "type": entry["type"],
                "default_opacity": metadata.get("default_opacity", 0.65),
                "coverage": entry.get("coverage"),
                "requires_key": bool(metadata.get("requires_key", False)),
                "url": metadata.get("url"),
                "layers": metadata.get("layers"),
                "layer_id": metadata.get("layer_id"),
                "tile_matrix_set": metadata.get("tile_matrix_set"),
                "wmts_format": metadata.get("wmts_format"),
                "wmts_style": metadata.get("wmts_style"),
                "wms_version": metadata.get("wms_version"),
                "wms_exceptions": metadata.get("wms_exceptions"),
                "bounds": metadata.get("bounds"),
                "attribution": metadata.get("attribution"),
            }
            url_template = metadata.get("url_template")
            if isinstance(url_template, str) and entry.get("provider") == "tomtom":
                overlay["url"] = (
                    url_template.replace("{api_key}", tomtom_key) if tomtom_key else None
                )
            is_available = not overlay["requires_key"] or bool(overlay.get("url"))
            overlay["is_available"] = is_available
            overlay["availability_reason"] = (
                f"{entry.get('provider', 'Provider').capitalize()} API key is not configured."
                if overlay["requires_key"] and not is_available
                else None
            )
            mapped.append(overlay)
        return mapped

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
