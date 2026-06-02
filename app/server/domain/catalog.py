from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryReferenceEntry:
    iso2: str
    name: str


@dataclass(frozen=True)
class CountryAliasReferenceEntry:
    alias: str
    iso2: str


@dataclass(frozen=True)
class GeospatialLayerReferenceEntry:
    layer_id: str
    display_name: str
    group: str
    provider: str | None
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class GibsTileMatrixSetReferenceEntry:
    tile_matrix_set_id: str
    meters_per_pixel: float


@dataclass(frozen=True)
class GibsLayerDefaultReferenceEntry:
    layer_id: str
    native_resolution_m: float | None
    date_fallback_days: int | None


@dataclass(frozen=True)
class ReferenceCatalog:
    countries: tuple[CountryReferenceEntry, ...]
    country_aliases: tuple[CountryAliasReferenceEntry, ...]
    geospatial_layers: tuple[GeospatialLayerReferenceEntry, ...]
    gibs_tile_matrix_sets: tuple[GibsTileMatrixSetReferenceEntry, ...]
    gibs_layer_defaults: tuple[GibsLayerDefaultReferenceEntry, ...]
