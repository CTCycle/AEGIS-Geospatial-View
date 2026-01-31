from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from AEGIS.server.utils.constants import COMMON_GEOSPATIAL_LAYERS

type LayerDefinition = dict[str, Any]
type ResolutionProvider = Callable[[str], tuple[float, ...] | list[float]]

__all__ = [
    "LayerProviderError",
    "LayerProviderNotFoundError",
    "LayerProviderEntry",
    "LayerProviderService",
]


###############################################################################
@dataclass(frozen=True)
class LayerProviderEntry:
    name: str
    provider: str
    label: str
    aliases: tuple[str, ...]
    resolution_m: float | None = None


###############################################################################
class LayerProviderError(Exception):
    """Base exception raised when a layer provider cannot fulfill a request."""


###############################################################################
class LayerProviderNotFoundError(LayerProviderError):
    """Raised when a requested layer does not have a registered provider."""


DEFAULT_LAYER_DEFINITIONS: dict[str, LayerDefinition] = {
    # Daily/NRT GIBS layers
    "VIIRS_SNPP_CorrectedReflectance_TrueColor": {
        "provider": "gibs",
        "aliases": (
            "truecolor",
            "true color",
            "viirs truecolor",
            "true color satellite",
            "satellite imagery",
        ),
    },
    "MODIS_Terra_Aerosol": {
        "provider": "gibs",
        "aliases": (
            "aerosol",
            "aerosol optical depth",
            "modis aerosol",
            "aod",
            "air pollution",
        ),
    },
    "MODIS_Terra_Land_Surface_Temp_Day": {
        "provider": "gibs",
        "aliases": (
            "surface temperature day",
            "land surface temperature",
            "lst day",
            "modis lst",
            "temperature day",
        ),
    },
    "MODIS_Terra_Land_Surface_Temp_Night": {
        "provider": "gibs",
        "aliases": (
            "surface temperature night",
            "lst night",
            "temperature night",
            "night temperature",
        ),
    },
    "MODIS_Terra_NDVI_8Day": {
        "provider": "gibs",
        "aliases": (
            "ndvi",
            "vegetation index",
            "modis ndvi",
            "vegetation",
            "greenness",
        ),
    },
    "MODIS_Terra_L3_Land_Water_Mask": {
        "provider": "gibs",
        "aliases": (
            "land/water mask",
            "water mask",
            "land water mask",
            "coastline",
        ),
    },
    "IMERG_Precipitation_Rate": {
        "provider": "gibs",
        "aliases": (
            "precipitation rate",
            "imerg precipitation",
            "imerg",
            "rain",
            "rainfall",
        ),
    },
    "VIIRS_SNPP_DayNightBand_ENCC": {
        "provider": "gibs",
        "aliases": (
            "nighttime lights",
            "city lights",
            "viirs lights",
            "light pollution",
            "night lights",
        ),
    },
    "MODIS_Combined_Thermal_Anomalies_Fire": {
        "provider": "gibs",
        "aliases": (
            "active fires",
            "fire",
            "fires",
            "thermal anomalies",
            "wildfire",
        ),
    },
    "OMPS_Ozone_Total_Column": {
        "provider": "gibs",
        "aliases": (
            "ozone",
            "ozone column",
            "total ozone",
            "omps ozone",
            "atmospheric ozone",
        ),
    },
    # Annual/static GIBS layers
    "MODIS_Combined_L3_IGBP_Land_Cover_Type_Annual": {
        "provider": "gibs",
        "aliases": (
            "land cover",
            "land cover type",
            "modis igbp land cover",
            "igbp land cover",
            "land use",
        ),
    },
    "SRTM_Color_Index": {
        "provider": "gibs",
        "aliases": (
            "elevation",
            "dem",
            "digital elevation model",
            "terrain",
            "topography",
        ),
    },
    # External API providers (non-GIBS)
    "OpenAQ_Air_Quality": {
        "provider": "openaq",
        "aliases": (
            "air quality",
            "air pollution",
            "pm2.5",
            "pm25",
            "pollution",
            "aqi",
        ),
    },
}


###############################################################################
class LayerProviderService:
    def __init__(
        self,
        layer_definitions: dict[str, LayerDefinition] | None = None,
        metadata_provider: ResolutionProvider | None = None,
    ) -> None:
        self.metadata_provider = metadata_provider
        self.layer_definitions = self._build_entries(
            layer_definitions or DEFAULT_LAYER_DEFINITIONS
        )
        self.alias_lookup = self._build_alias_index(self.layer_definitions)

    # -------------------------------------------------------------------------
    def _build_entries(
        self, layer_definitions: dict[str, LayerDefinition]
    ) -> dict[str, LayerProviderEntry]:
        entries: dict[str, LayerProviderEntry] = {}
        for name, specification in layer_definitions.items():
            provider = str(specification.get("provider") or "").strip().lower()
            if not provider:
                continue
            metadata_label = COMMON_GEOSPATIAL_LAYERS.get(name)
            label = str(specification.get("label") or metadata_label or name).strip()
            aliases = tuple(
                str(value).strip()
                for value in specification.get("aliases", ())
                if str(value).strip()
            )
            resolution_value = self._resolve_resolution(name)
            entries[name] = LayerProviderEntry(
                name=name,
                provider=provider,
                label=label,
                aliases=aliases,
                resolution_m=resolution_value,
            )
        return entries

    # -------------------------------------------------------------------------
    def _resolve_resolution(self, layer_name: str) -> float | None:
        if self.metadata_provider is None:
            return None
        try:
            values = self.metadata_provider(layer_name)
        except Exception:
            return None
        if not values:
            return None
        normalized: list[float] = []
        for value in values:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric > 0:
                normalized.append(numeric)
        if not normalized:
            return None
        return min(normalized)

    # -------------------------------------------------------------------------
    def _build_alias_index(
        self, entries: dict[str, LayerProviderEntry]
    ) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for entry in entries.values():
            lookup[entry.name.lower()] = entry.name
            lookup[entry.label.lower()] = entry.name
            for alias in entry.aliases:
                lookup[alias.lower()] = entry.name
        return lookup

    # -------------------------------------------------------------------------
    def list_options(self) -> dict[str, str]:
        return {entry.name: entry.label for entry in self.layer_definitions.values()}

    # -------------------------------------------------------------------------
    def resolve(self, value: str) -> LayerProviderEntry:
        normalized = (value or "").strip()
        if not normalized:
            raise LayerProviderNotFoundError("Layer selection is required.")
        key = normalized.lower()
        canonical = self.alias_lookup.get(key)
        if canonical is None:
            raise LayerProviderNotFoundError(f"Layer '{normalized}' is not available.")
        return self.layer_definitions[canonical]

    # -------------------------------------------------------------------------
    def describe(self, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            entry = self.resolve(value)
        except LayerProviderError:
            return value
        return entry.label
