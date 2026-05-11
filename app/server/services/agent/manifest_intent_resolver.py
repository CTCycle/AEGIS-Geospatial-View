from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from server.domain.extraction.models import TurnParseResult
from server.services.geospatial.capability_registry import CapabilityRegistry


def _tokenize(value: object) -> set[str]:
    if value is None:
        return set()
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    base_parts = [part for part in re.split(r"[^\w]+", text, flags=re.UNICODE) if part]
    tokens: set[str] = set(base_parts)
    for part in base_parts:
        tokens.update(chunk for chunk in part.split("_") if chunk)
    return tokens


def _collect_tokens(values: object) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, dict):
        tokens: set[str] = set()
        for item in values.values():
            tokens.update(_collect_tokens(item))
        return tokens
    if isinstance(values, (list, tuple, set)):
        tokens: set[str] = set()
        for item in values:
            tokens.update(_collect_tokens(item))
        return tokens
    return _tokenize(values)


@dataclass(frozen=True)
class ManifestResolution:
    basemap_id: str
    overlay_ids: list[str] = field(default_factory=list)
    tool_id: str | None = None
    ambiguous_concepts: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)


class ManifestIntentResolver:
    OVERLAY_EXCLUDED_CONCEPTS = {
        "a",
        "an",
        "and",
        "are",
        "area",
        "areas",
        "around",
        "above",
        "conditions",
        "context",
        "display",
        "for",
        "from",
        "kind",
        "kinds",
        "layer",
        "layers",
        "map",
        "maps",
        "basemap",
        "base",
        "me",
        "moving",
        "near",
        "nearby",
        "now",
        "of",
        "on",
        "over",
        "requested",
        "right",
        "show",
        "situation",
        "satellite",
        "imagery",
        "terrain",
        "topographic",
        "topography",
        "dark",
        "light",
        "style",
        "view",
        "forecast",
        "current",
        "direct",
        "query",
        "search",
        "location",
        "type",
        "types",
        "view",
        "where",
    }

    OVERLAY_CONCEPT_ALLOWLISTS = (
        (
            {"rain", "rainfall", "precipitation", "storm", "storms"},
            {
                "rainviewer_precipitation_radar",
                "IMERG_Precipitation_Rate",
                "openmeteo_weather_forecast",
                "openmeteo_pressure_humidity_wind",
                "noaa_radar",
                "noaa_weather_alerts",
            },
        ),
        (
            {
                "fire",
                "fires",
                "wildfire",
                "wildfires",
                "hotspot",
                "hotspots",
                "thermal",
                "active_fire",
            },
            {"MODIS_Combined_Thermal_Anomalies_Fire", "nasa_firms_active_fires"},
        ),
        (
            {"smoke", "smoky", "dust", "dusty", "aerosol", "aerosols"},
            {
                "MODIS_Terra_Aerosol",
                "openmeteo_air_quality_forecast",
                "openaq_air_quality",
            },
        ),
        (
            {"air", "air_quality", "pollution", "polluted", "pm25", "pm2", "quality"},
            {
                "openmeteo_air_quality_forecast",
                "openaq_air_quality",
                "MODIS_Terra_Aerosol",
            },
        ),
        ({"ozone"}, {"OMPS_Ozone_Total_Column"}),
        (
            {"vegetation", "green", "greenness", "ndvi"},
            {
                "MODIS_Terra_NDVI_8Day",
                "esa_worldcover",
                "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual",
                "MODIS_Terra_L3_Land_Water_Mask",
            },
        ),
        (
            {"land", "land_cover", "landcover", "forest", "forests", "farm", "farms", "water"},
            {
                "esa_worldcover",
                "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual",
                "MODIS_Terra_L3_Land_Water_Mask",
            },
        ),
        (
            {
                "terrain",
                "elevation",
                "relief",
                "hills",
                "hill",
                "topography",
                "topographic",
            },
            {"SRTM_Color_Index"},
        ),
        (
            {"heat", "temperature", "ground", "surface"},
            {
                "MODIS_Terra_Land_Surface_Temp_Day",
                "MODIS_Terra_Land_Surface_Temp_Night",
                "openmeteo_weather_forecast",
            },
        ),
        ({"night", "lights", "light"}, {"VIIRS_SNPP_DayNightBand_ENCC"}),
        ({"solar", "photovoltaic", "pv"}, {"pvgis_solar"}),
        ({"noise", "noisy"}, {"eea_noise_2019"}),
        ({"traffic", "congestion"}, {"tomtom_traffic_flow"}),
        (
            {"flood", "flooding", "floodplain", "flood_zone", "floodzone"},
            {
                "fema_nfhl_flood_zones",
                "usgs_water_gauges",
                "noaa_coops_water_levels",
                "noaa_weather_alerts",
            },
        ),
        (
            {"earthquake", "earthquakes", "seismic", "quake", "quakes"},
            {"usgs_earthquakes"},
        ),
        (
            {"weather", "alert", "alerts", "warning", "watch", "storm"},
            {"noaa_weather_alerts", "noaa_radar", "openmeteo_weather_forecast"},
        ),
        (
            {"rivers", "river", "lakes", "lake", "hydrography"},
            {"census_tigerweb_hydrography"},
        ),
        (
            {"population", "demographics", "demographic"},
            {"census_tigerweb_demographics"},
        ),
        (
            {"amenities", "services", "places", "poi"},
            {"overpass_poi_amenities", "geoapify_amenities"},
        ),
        (
            {
                "webcam",
                "webcams",
                "camera",
                "cameras",
                "live",
                "visual",
                "view",
                "road",
                "beach",
                "ski",
            },
            {"windy_webcams"},
        ),
        (
            {
                "transit",
                "bus",
                "train",
                "station",
                "stop",
                "stops",
                "route",
                "routes",
                "delay",
                "delays",
                "disruption",
                "disruptions",
                "vehicle",
                "vehicles",
            },
            {"gtfs_static", "gtfs_realtime", "transitland_feeds"},
        ),
    )

    def resolve(
        self,
        *,
        turn: TurnParseResult,
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> ManifestResolution:
        concepts = self._extract_concepts(turn)
        basemap_id = self._select_basemap(concepts, capability_registry, available_ids)
        overlay_ids = self._select_overlays(
            concepts, capability_registry, available_ids
        )
        tool_id = self._select_tool(concepts, capability_registry, available_ids)
        return ManifestResolution(
            basemap_id=basemap_id,
            overlay_ids=overlay_ids,
            tool_id=tool_id,
            ambiguous_concepts=[],
            concepts=concepts,
        )

    def _extract_concepts(self, turn: TurnParseResult) -> list[str]:
        intent = turn.normalized_intent
        ordered_signals: list[object] = [
            *intent.requested_visualizations,
            *intent.intent_tags,
            *intent.task_tags,
            intent.intent_id,
            intent.intent_label,
        ]
        seen: set[str] = set()
        concepts: list[str] = []
        for signal in ordered_signals:
            for token in sorted(_collect_tokens(signal)):
                if token in seen:
                    continue
                seen.add(token)
                concepts.append(token)
        return concepts

    def _capability_exists(
        self,
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
        capability_id: str,
    ) -> bool:
        return (
            capability_id in available_ids
            and capability_registry.get_capability(capability_id) is not None
        )

    def _iter_kind(
        self, capability_registry: CapabilityRegistry, kind: str
    ) -> list[dict[str, object]]:
        if kind == "basemap":
            return capability_registry.list_basemaps()
        if kind == "overlay":
            return [
                *capability_registry.list_overlays(),
                *capability_registry.list_cameras(),
                *capability_registry.list_transit(),
            ]
        if kind == "tool":
            return capability_registry.list_tools()
        return []

    def _capability_tokens(self, capability: dict[str, object]) -> set[str]:
        metadata = capability.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        sources: list[object] = [
            capability.get("capabilities"),
            metadata.get("intent_tags"),
            metadata.get("task_tags"),
            metadata.get("keywords"),
            metadata.get("map_type_tags"),
        ]
        return _collect_tokens(sources)

    def _rank_kind(
        self,
        *,
        kind: str,
        concepts: list[str],
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> list[tuple[str, int]]:
        ranked: list[tuple[str, int]] = []
        concept_set = set(concepts)
        for capability in self._iter_kind(capability_registry, kind):
            capability_id = str(capability.get("id") or "").strip()
            if not capability_id:
                continue
            if not self._capability_exists(
                capability_registry, available_ids, capability_id
            ):
                continue
            score = len(concept_set.intersection(self._capability_tokens(capability)))
            ranked.append((capability_id, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    def _select_basemap(
        self,
        concepts: list[str],
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> str:
        ranked = self._rank_kind(
            kind="basemap",
            concepts=concepts,
            capability_registry=capability_registry,
            available_ids=available_ids,
        )
        for capability_id, score in ranked:
            if score > 0:
                return capability_id
        return "osm_default" if "osm_default" in available_ids else "osm_default"

    def _select_overlays(
        self,
        concepts: list[str],
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> list[str]:
        allowed_overlay_ids = self._allowed_overlay_ids(concepts)
        overlays = {
            str(item.get("id")): self._capability_tokens(item)
            for item in capability_registry.list_overlays()
            + capability_registry.list_cameras()
            + capability_registry.list_transit()
            if isinstance(item, dict)
            and str(item.get("id") or "") in available_ids
            and (
                not allowed_overlay_ids
                or str(item.get("id") or "") in allowed_overlay_ids
            )
            and self._capability_exists(
                capability_registry, available_ids, str(item.get("id") or "")
            )
        }
        selected: list[str] = []
        concept_set = set(concepts)
        for concept in concepts:
            if concept in self.OVERLAY_EXCLUDED_CONCEPTS:
                continue
            concept_candidates = [
                capability_id
                for capability_id, tokens in overlays.items()
                if concept in tokens and capability_id not in selected
            ]
            if not concept_candidates:
                continue
            concept_candidates.sort(
                key=lambda capability_id: (
                    len(overlays[capability_id].intersection(concept_set)),
                    capability_id,
                ),
                reverse=True,
            )
            selected.append(concept_candidates[0])
            if len(selected) >= 4:
                return selected

        ranked = self._rank_kind(
            kind="overlay",
            concepts=concepts,
            capability_registry=capability_registry,
            available_ids=available_ids,
        )
        for capability_id, score in ranked:
            if score <= 0 or capability_id in selected:
                continue
            if allowed_overlay_ids and capability_id not in allowed_overlay_ids:
                continue
            selected.append(capability_id)
            if len(selected) >= 4:
                break
        return selected

    def _allowed_overlay_ids(self, concepts: list[str]) -> set[str]:
        concept_set = set(concepts)
        allowed: set[str] = set()
        for markers, overlay_ids in self.OVERLAY_CONCEPT_ALLOWLISTS:
            if concept_set.intersection(markers):
                allowed.update(overlay_ids)
        return allowed

    def _select_tool(
        self,
        concepts: list[str],
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> str | None:
        ranked = self._rank_kind(
            kind="tool",
            concepts=concepts,
            capability_registry=capability_registry,
            available_ids=available_ids,
        )
        for capability_id, score in ranked:
            if score > 0:
                return capability_id
        if self._capability_exists(
            capability_registry, available_ids, "location_to_coordinates"
        ):
            return "location_to_coordinates"
        return None
