from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.common.constants import PROJECT_DIR
from server.domain.catalog import (
    CountryAliasReferenceEntry,
    CountryReferenceEntry,
    GeospatialLayerReferenceEntry,
    GibsLayerDefaultReferenceEntry,
    GibsTileMatrixSetReferenceEntry,
    ReferenceCatalog,
)

REFERENCE_CATALOG_DIR_NAME = "reference"
COUNTRIES_REFERENCE_FILE_NAME = "countries.json"
GEOSPATIAL_LAYERS_REFERENCE_FILE_NAME = "geospatial_layers.json"
GIBS_TILE_MATRIX_SETS_REFERENCE_FILE_NAME = "gibs_tile_matrix_sets.json"
GIBS_LAYER_DEFAULTS_REFERENCE_FILE_NAME = "gibs_layer_defaults.json"


def get_catalog_root() -> Path:
    return Path(PROJECT_DIR) / "resources" / "catalog"


def load_reference_catalog(catalog_root: Path | None = None) -> ReferenceCatalog:
    root = (catalog_root or get_catalog_root()) / REFERENCE_CATALOG_DIR_NAME
    countries_payload = _load_json_file(root / COUNTRIES_REFERENCE_FILE_NAME)
    layers_payload = _load_json_file(root / GEOSPATIAL_LAYERS_REFERENCE_FILE_NAME)
    tile_matrix_payload = _load_json_file(
        root / GIBS_TILE_MATRIX_SETS_REFERENCE_FILE_NAME
    )
    layer_defaults_payload = _load_json_file(
        root / GIBS_LAYER_DEFAULTS_REFERENCE_FILE_NAME
    )

    countries = _parse_countries(countries_payload)
    country_aliases = _parse_country_aliases(countries_payload, countries)
    geospatial_layers = _parse_geospatial_layers(layers_payload)
    gibs_tile_matrix_sets = _parse_gibs_tile_matrix_sets(tile_matrix_payload)
    gibs_layer_defaults = _parse_gibs_layer_defaults(layer_defaults_payload)
    return ReferenceCatalog(
        countries=tuple(countries),
        country_aliases=tuple(country_aliases),
        geospatial_layers=tuple(geospatial_layers),
        gibs_tile_matrix_sets=tuple(gibs_tile_matrix_sets),
        gibs_layer_defaults=tuple(gibs_layer_defaults),
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Reference catalog file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Reference catalog file must contain an object: {path}")
    return payload


def _normalize_alias_key(value: str) -> str:
    return value.strip().casefold()


def _require_string(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return normalized


def _require_iso2(value: Any, *, field_name: str) -> str:
    normalized = _require_string(value, field_name=field_name).upper()
    if len(normalized) != 2:
        raise ValueError(f"{field_name} must be a two-letter ISO2 code.")
    return normalized


def _parse_countries(payload: dict[str, Any]) -> list[CountryReferenceEntry]:
    entries = payload.get("countries")
    if not isinstance(entries, list):
        raise ValueError("countries.json must contain a countries list.")
    seen_iso2: set[str] = set()
    countries: list[CountryReferenceEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Country entries must be objects.")
        iso2 = _require_iso2(item.get("iso2"), field_name="country.iso2")
        name = _require_string(item.get("name"), field_name="country.name")
        if iso2 in seen_iso2:
            raise ValueError(f"Duplicate country ISO2 code: {iso2}")
        seen_iso2.add(iso2)
        countries.append(CountryReferenceEntry(iso2=iso2, name=name))
    return countries


def _parse_country_aliases(
    payload: dict[str, Any],
    countries: list[CountryReferenceEntry],
) -> list[CountryAliasReferenceEntry]:
    entries = payload.get("aliases")
    if not isinstance(entries, list):
        raise ValueError("countries.json must contain an aliases list.")
    valid_iso2 = {entry.iso2 for entry in countries}
    seen_aliases: set[str] = set()
    aliases: list[CountryAliasReferenceEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Country alias entries must be objects.")
        alias = _require_string(item.get("alias"), field_name="alias.alias")
        alias_key = _normalize_alias_key(alias)
        if not alias_key:
            raise ValueError("Country aliases must not normalize to an empty key.")
        if alias_key in seen_aliases:
            raise ValueError(f"Duplicate country alias key: {alias}")
        iso2 = _require_iso2(item.get("iso2"), field_name="alias.iso2")
        if iso2 not in valid_iso2:
            raise ValueError(f"Country alias references unknown ISO2 code: {iso2}")
        seen_aliases.add(alias_key)
        aliases.append(CountryAliasReferenceEntry(alias=alias, iso2=iso2))
    return aliases


def _parse_geospatial_layers(
    payload: dict[str, Any],
) -> list[GeospatialLayerReferenceEntry]:
    entries = payload.get("layers")
    if not isinstance(entries, list):
        raise ValueError("geospatial_layers.json must contain a layers list.")
    seen_layer_ids: set[str] = set()
    layers: list[GeospatialLayerReferenceEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Geospatial layer entries must be objects.")
        layer_id = _require_string(item.get("layerId"), field_name="layer.layerId")
        if layer_id in seen_layer_ids:
            raise ValueError(f"Duplicate geospatial layer ID: {layer_id}")
        display_name = _require_string(
            item.get("displayName"),
            field_name="layer.displayName",
        )
        group = _require_string(item.get("group"), field_name="layer.group")
        provider_value = item.get("provider")
        provider = str(provider_value).strip() if provider_value is not None else None
        aliases = _parse_string_list(item.get("aliases"), field_name="layer.aliases")
        keywords = _parse_string_list(item.get("keywords"), field_name="layer.keywords")
        seen_layer_ids.add(layer_id)
        layers.append(
            GeospatialLayerReferenceEntry(
                layer_id=layer_id,
                display_name=display_name,
                group=group,
                provider=provider or None,
                aliases=aliases,
                keywords=keywords,
            )
        )
    return layers


def _parse_gibs_tile_matrix_sets(
    payload: dict[str, Any],
) -> list[GibsTileMatrixSetReferenceEntry]:
    entries = payload.get("tileMatrixSets")
    if not isinstance(entries, list):
        raise ValueError(
            "gibs_tile_matrix_sets.json must contain a tileMatrixSets list."
        )
    seen_ids: set[str] = set()
    tile_matrix_sets: list[GibsTileMatrixSetReferenceEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("GIBS tile matrix set entries must be objects.")
        tile_matrix_set_id = _require_string(
            item.get("tileMatrixSetId"),
            field_name="tileMatrixSet.tileMatrixSetId",
        )
        if tile_matrix_set_id in seen_ids:
            raise ValueError(f"Duplicate tile matrix set ID: {tile_matrix_set_id}")
        try:
            meters_per_pixel = float(item.get("metersPerPixel"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid metersPerPixel for tile matrix set '{tile_matrix_set_id}'."
            ) from exc
        if meters_per_pixel <= 0:
            raise ValueError(
                f"metersPerPixel must be positive for '{tile_matrix_set_id}'."
            )
        seen_ids.add(tile_matrix_set_id)
        tile_matrix_sets.append(
            GibsTileMatrixSetReferenceEntry(
                tile_matrix_set_id=tile_matrix_set_id,
                meters_per_pixel=meters_per_pixel,
            )
        )
    return tile_matrix_sets


def _parse_gibs_layer_defaults(
    payload: dict[str, Any],
) -> list[GibsLayerDefaultReferenceEntry]:
    entries = payload.get("layerDefaults")
    if not isinstance(entries, list):
        raise ValueError("gibs_layer_defaults.json must contain a layerDefaults list.")
    seen_layer_ids: set[str] = set()
    defaults: list[GibsLayerDefaultReferenceEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("GIBS layer default entries must be objects.")
        layer_id = _require_string(
            item.get("layerId"), field_name="layerDefault.layerId"
        )
        if layer_id in seen_layer_ids:
            raise ValueError(f"Duplicate GIBS layer default for layer '{layer_id}'.")
        native_resolution_value = item.get("nativeResolutionM")
        date_fallback_value = item.get("dateFallbackDays")
        native_resolution_m = (
            float(native_resolution_value)
            if native_resolution_value is not None
            else None
        )
        date_fallback_days = (
            int(date_fallback_value) if date_fallback_value is not None else None
        )
        if native_resolution_m is None and date_fallback_days is None:
            raise ValueError(
                f"GIBS layer default '{layer_id}' must define at least one value."
            )
        seen_layer_ids.add(layer_id)
        defaults.append(
            GibsLayerDefaultReferenceEntry(
                layer_id=layer_id,
                native_resolution_m=native_resolution_m,
                date_fallback_days=date_fallback_days,
            )
        )
    return defaults


def _parse_string_list(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return tuple()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list.")
    normalized: list[str] = []
    for item in value:
        entry = _require_string(item, field_name=field_name)
        normalized.append(entry)
    return tuple(normalized)
