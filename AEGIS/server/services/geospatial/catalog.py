from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from AEGIS.server.services.geospatial.openaq import OpenAQService
from AEGIS.server.services.geospatial.pvgis import PVGISService
from AEGIS.server.utils.constants import COMMON_GEOSPATIAL_LAYERS
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
        providers = [
            {
                "id": "tomtom",
                "name": "TomTom",
                "docs_url": "https://developer.tomtom.com/",
                "commercial_notes": "Commercial use allowed under TomTom terms.",
                "warning_level": "medium",
            },
            {
                "id": "geoapify",
                "name": "Geoapify",
                "docs_url": "https://www.geoapify.com/",
                "commercial_notes": "Free tier supports limited commercial use with attribution.",
                "warning_level": "medium",
            },
            {
                "id": "openaq",
                "name": "OpenAQ",
                "docs_url": "https://docs.openaq.org/",
                "commercial_notes": "Coverage is uneven and source licenses vary by station.",
                "warning_level": "medium",
            },
            {
                "id": "eea",
                "name": "EEA",
                "docs_url": "https://www.eea.europa.eu/",
                "commercial_notes": "EU-focused institutional datasets; service shape may change.",
                "warning_level": "medium",
            },
            {
                "id": "esa",
                "name": "ESA",
                "docs_url": "https://services.terrascope.be/",
                "commercial_notes": "Attribution required for WorldCover services.",
                "warning_level": "low",
            },
            {
                "id": "pvgis",
                "name": "PVGIS",
                "docs_url": "https://re.jrc.ec.europa.eu/pvg_tools/en/",
                "commercial_notes": "PVGIS results are generally reusable; attribution recommended.",
                "warning_level": "low",
            },
            {
                "id": "gibs",
                "name": "NASA GIBS",
                "docs_url": "https://earthdata.nasa.gov/eosdis/science-system-description/eosdis-components/gibs",
                "commercial_notes": "NASA imagery requires attribution and service-aware usage.",
                "warning_level": "low",
            },
        ]

        basemaps = [
            {
                "id": "osm_default",
                "label": "OpenStreetMap",
                "provider": "fallback",
                "type": "tile",
                "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "attribution": "© OpenStreetMap contributors",
                "requires_key": False,
            },
            {
                "id": "tomtom_basic",
                "label": "TomTom Basic",
                "provider": "tomtom",
                "type": "tile",
                "tile_url": (
                    f"https://api.tomtom.com/map/1/tile/basic/main/{{z}}/{{x}}/{{y}}.png?key={tomtom_key}"
                    if tomtom_key
                    else None
                ),
                "attribution": "© TomTom",
                "requires_key": True,
            },
            {
                "id": "geoapify_osm",
                "label": "Geoapify OSM Bright",
                "provider": "geoapify",
                "type": "tile",
                "tile_url": (
                    f"https://maps.geoapify.com/v1/tile/osm-bright/{{z}}/{{x}}/{{y}}.png?apiKey={geoapify_key}"
                    if geoapify_key
                    else None
                ),
                "attribution": "© OpenMapTiles © OpenStreetMap contributors © Geoapify",
                "requires_key": True,
            },
        ]

        overlays: list[JsonDict] = [
            {
                "id": "tomtom_traffic_flow",
                "label": "TomTom Traffic Flow",
                "provider": "tomtom",
                "type": "tile",
                "default_opacity": 0.7,
                "coverage": "global",
                "requires_key": True,
                "url": (
                    f"https://api.tomtom.com/traffic/map/4/tile/flow/absolute/{{z}}/{{x}}/{{y}}.png?key={tomtom_key}"
                    if tomtom_key
                    else None
                ),
                "attribution": "© TomTom",
            },
            {
                "id": "geoapify_amenities",
                "label": "Geoapify Places (Amenities)",
                "provider": "geoapify",
                "type": "geojson",
                "default_opacity": 0.9,
                "coverage": "global",
                "requires_key": True,
                "attribution": "© Geoapify",
            },
            {
                "id": "eea_noise_2019",
                "label": "EEA Noise Exposure 2019",
                "provider": "eea",
                "type": "wms",
                "default_opacity": 0.55,
                "coverage": "eu-eea",
                "requires_key": False,
                "url": "https://noise.discomap.eea.europa.eu/arcgis/services/noiseStoryMap/noise_exposure_2019/MapServer/WMSServer",
                "layers": "0",
                "wms_version": "1.1.1",
                "wms_exceptions": "application/vnd.ogc.se_inimage",
                # Approximate Europe/EEA extent in EPSG:4326 to reduce out-of-coverage
                # tile requests that trigger ArcGIS WMS errors.
                "bounds": [-35.0, 24.0, 45.0, 72.0],
                "attribution": "© European Environment Agency (CC BY 4.0 where applicable)",
            },
            {
                "id": "esa_worldcover",
                "label": "ESA WorldCover",
                "provider": "esa",
                "type": "wmts",
                "default_opacity": 0.45,
                "coverage": "global",
                "requires_key": False,
                "url": "https://services.terrascope.be/wmts/v2",
                "layer_id": "WORLDCOVER_2021_MAP",
                "tile_matrix_set": "EPSG:3857",
                "wmts_format": "image/png",
                "wmts_style": "",
                "attribution": "© ESA WorldCover / Terrascope",
            },
            {
                "id": "openaq_air_quality",
                "label": "OpenAQ Air Quality",
                "provider": "openaq",
                "type": "point-insight",
                "default_opacity": 1.0,
                "coverage": "global-partial",
                "requires_key": False,
                "attribution": "© OpenAQ and source providers",
            },
            {
                "id": "pvgis_solar",
                "label": "PVGIS Solar Potential",
                "provider": "pvgis",
                "type": "point-insight",
                "default_opacity": 1.0,
                "coverage": "global-except-poles",
                "requires_key": False,
                "attribution": "© European Commission JRC PVGIS",
            },
        ]
        for layer_id, layer_label in COMMON_GEOSPATIAL_LAYERS.items():
            overlays.append(
                {
                    "id": f"GIBS_{layer_id}",
                    "label": layer_label,
                    "provider": "gibs",
                    "type": "legacy-image",
                    "default_opacity": 0.68,
                    "coverage": "global",
                    "requires_key": False,
                    "attribution": "© NASA GIBS",
                }
            )
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
            try:
                await self._apply_rate_limit("openaq")
                insights["air_quality"] = await self.openaq_service.get_nearby_measurements(
                    latitude, longitude, radius_m
                )
            except Exception as exc:
                logger.warning("OpenAQ insight failed: %s", exc)
                insights["air_quality"] = {"error": "OpenAQ data unavailable"}
        if "pvgis_solar" in overlay_ids:
            try:
                await self._apply_rate_limit("pvgis")
                insights["solar_potential"] = await self.pvgis_service.get_point_estimate(
                    latitude, longitude
                )
            except Exception as exc:
                logger.warning("PVGIS insight failed: %s", exc)
                insights["solar_potential"] = {"error": "PVGIS data unavailable"}

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
