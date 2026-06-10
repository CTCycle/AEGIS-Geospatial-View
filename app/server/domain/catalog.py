from __future__ import annotations

from pydantic import BaseModel


class CountryReferenceEntry(BaseModel):
    iso2: str
    name: str


class CountryAliasReferenceEntry(BaseModel):
    alias: str
    iso2: str


class GeospatialLayerReferenceEntry(BaseModel):
    layer_id: str
    display_name: str
    group: str
    provider: str | None
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


class GibsTileMatrixSetReferenceEntry(BaseModel):
    tile_matrix_set_id: str
    meters_per_pixel: float


class GibsLayerDefaultReferenceEntry(BaseModel):
    layer_id: str
    native_resolution_m: float | None
    date_fallback_days: int | None


class ReferenceCatalog(BaseModel):
    countries: tuple[CountryReferenceEntry, ...] = ()
    country_aliases: tuple[CountryAliasReferenceEntry, ...] = ()
    geospatial_layers: tuple[GeospatialLayerReferenceEntry, ...] = ()
    gibs_tile_matrix_sets: tuple[GibsTileMatrixSetReferenceEntry, ...] = ()
    gibs_layer_defaults: tuple[GibsLayerDefaultReferenceEntry, ...] = ()
