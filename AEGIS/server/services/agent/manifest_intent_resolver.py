from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from AEGIS.server.domain.extraction.models import TurnParseResult
from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry


def _norm(value: object) -> str:
    text = str(value or "").lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


@dataclass(frozen=True)
class ManifestResolution:
    basemap_id: str
    overlay_ids: list[str] = field(default_factory=list)
    tool_id: str | None = None
    ambiguous_concepts: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)


class ManifestIntentResolver:
    CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
        "satellite": ("satellite", "imagery", "truecolor", "true_color"),
        "terrain": ("terrain", "topographic", "topography", "relief"),
        "elevation": ("elevation", "dem", "srtm"),
        "air_quality": ("air_quality", "air-quality", "pollution", "pollutant", "polluted"),
        "aerosol": ("aerosol", "atmospheric_pollution"),
        "traffic": ("traffic", "congestion", "road_flow", "traffic_flow"),
        "precipitation": ("precipitation", "rain", "storm", "radar", "rainfall"),
        "weather": ("weather", "forecast", "temperature"),
        "poi": ("poi", "points_of_interest", "amenities", "commercial", "nearby"),
        "active_fire": ("active_fire", "active_fires", "wildfire", "wildfires", "thermal_anomaly", "thermal_anomalies"),
        "land_cover": ("land_cover", "landcover", "worldcover", "igbp"),
        "solar": ("solar", "pvgis", "photovoltaic"),
        "noise": ("noise", "environmental_noise"),
        "ozone": ("ozone",),
    }

    BASEMAP_BY_CONCEPT = {
        "satellite": "gibs_satellite",
        "terrain": "osm_terrain",
    }

    OVERLAYS_BY_CONCEPT = {
        "elevation": ("SRTM_Color_Index",),
        "air_quality": ("openaq_air_quality",),
        "aerosol": ("MODIS_Terra_Aerosol",),
        "traffic": ("tomtom_traffic_flow",),
        "precipitation": ("rainviewer_precipitation_radar", "IMERG_Precipitation_Rate"),
        "weather": ("openmeteo_weather_forecast",),
        "poi": ("overpass_poi_amenities",),
        "land_cover": ("MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual", "esa_worldcover"),
        "active_fire": ("MODIS_Combined_Thermal_Anomalies_Fire",),
        "solar": ("pvgis_solar",),
        "noise": ("eea_noise_2019",),
        "ozone": ("OMPS_Ozone_Total_Column",),
    }

    TOOL_BY_CONCEPT = {
        "air_quality": "get_air_quality_forecast",
        "weather": "get_weather_forecast",
        "poi": "get_nearby_poi",
    }

    def resolve(
        self,
        *,
        turn: TurnParseResult,
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> ManifestResolution:
        concepts = self._extract_concepts(turn)
        basemap_id = self._select_basemap(concepts, capability_registry, available_ids)
        overlay_ids, ambiguous = self._select_overlays(
            concepts, capability_registry, available_ids
        )
        tool_id = self._select_tool(concepts, capability_registry, available_ids)
        return ManifestResolution(
            basemap_id=basemap_id,
            overlay_ids=overlay_ids,
            tool_id=tool_id,
            ambiguous_concepts=ambiguous,
            concepts=concepts,
        )

    def _intent_text(self, turn: TurnParseResult) -> str:
        intent = turn.normalized_intent
        parts = [
            turn.user_text,
            intent.intent_id,
            intent.intent_label,
            *intent.task_tags,
            *intent.intent_tags,
            *intent.requested_visualizations,
        ]
        return " ".join(parts).lower()

    def _extract_concepts(self, turn: TurnParseResult) -> list[str]:
        normalized_text = _norm(self._intent_text(turn))
        found: list[str] = []
        for concept, aliases in self.CONCEPT_ALIASES.items():
            if any(alias in normalized_text for alias in {_norm(item) for item in aliases}):
                found.append(concept)
        return found

    def _capability_exists(
        self, capability_registry: CapabilityRegistry, available_ids: set[str], capability_id: str
    ) -> bool:
        return capability_id in available_ids and capability_registry.get_capability(capability_id) is not None

    def _select_basemap(
        self,
        concepts: list[str],
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> str:
        for concept in concepts:
            capability_id = self.BASEMAP_BY_CONCEPT.get(concept)
            if capability_id and self._capability_exists(
                capability_registry, available_ids, capability_id
            ):
                return capability_id
        return "osm_default" if "osm_default" in available_ids else "osm_default"

    def _select_overlays(
        self,
        concepts: list[str],
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> tuple[list[str], list[str]]:
        selected: list[str] = []
        ambiguous: list[str] = []
        for concept in concepts:
            candidates = [
                capability_id
                for capability_id in self.OVERLAYS_BY_CONCEPT.get(concept, ())
                if self._capability_exists(capability_registry, available_ids, capability_id)
            ]
            for capability_id in candidates[:1]:
                if capability_id not in selected:
                    selected.append(capability_id)
        return selected[:4], ambiguous

    def _select_tool(
        self,
        concepts: list[str],
        capability_registry: CapabilityRegistry,
        available_ids: set[str],
    ) -> str | None:
        for concept in concepts:
            capability_id = self.TOOL_BY_CONCEPT.get(concept)
            if capability_id and self._capability_exists(
                capability_registry, available_ids, capability_id
            ):
                return capability_id
        if self._capability_exists(capability_registry, available_ids, "location_to_coordinates"):
            return "location_to_coordinates"
        return None
