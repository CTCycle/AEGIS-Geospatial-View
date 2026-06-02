from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.services.catalog.reference_loader import get_catalog_root, load_reference_catalog


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_reference_root(tmp_path: Path) -> Path:
    root = tmp_path / "catalog" / "reference"
    root.mkdir(parents=True)
    _write_json(
        root / "countries.json",
        {
            "version": 1,
            "countries": [{"iso2": "MO", "name": "Macau SAR China"}],
            "aliases": [
                {"alias": "Macau SAR China", "iso2": "MO"},
                {"alias": "Macau", "iso2": "MO"},
            ],
        },
    )
    _write_json(
        root / "geospatial_layers.json",
        {
            "version": 1,
            "layers": [
                {
                    "layerId": "VIIRS_SNPP_CorrectedReflectance_TrueColor",
                    "displayName": "True Color Satellite (VIIRS, Daily)",
                    "group": "gibs_nrt",
                    "provider": "gibs",
                    "aliases": ["true color"],
                    "keywords": ["true color"],
                }
            ],
        },
    )
    _write_json(
        root / "gibs_tile_matrix_sets.json",
        {
            "version": 1,
            "tileMatrixSets": [{"tileMatrixSetId": "250m", "metersPerPixel": 250.0}],
        },
    )
    _write_json(
        root / "gibs_layer_defaults.json",
        {
            "version": 1,
            "layerDefaults": [
                {
                    "layerId": "VIIRS_SNPP_CorrectedReflectance_TrueColor",
                    "nativeResolutionM": 375.0,
                    "dateFallbackDays": 7,
                }
            ],
        },
    )
    return tmp_path / "catalog"


def test_loads_all_reference_files_from_catalog_root() -> None:
    catalog = load_reference_catalog(get_catalog_root())

    assert catalog.countries
    assert catalog.country_aliases
    assert catalog.geospatial_layers
    assert catalog.gibs_tile_matrix_sets
    assert catalog.gibs_layer_defaults


def test_country_aliases_must_resolve_to_existing_iso2(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "countries.json",
        {
            "version": 1,
            "countries": [{"iso2": "US", "name": "United States"}],
            "aliases": [{"alias": "USA", "iso2": "ZZ"}],
        },
    )

    with pytest.raises(ValueError, match="unknown ISO2"):
        load_reference_catalog(root)


def test_duplicate_country_alias_keys_fail(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "countries.json",
        {
            "version": 1,
            "countries": [{"iso2": "US", "name": "United States"}],
            "aliases": [
                {"alias": "USA", "iso2": "US"},
                {"alias": " usa ", "iso2": "US"},
            ],
        },
    )

    with pytest.raises(ValueError, match="Duplicate country alias key"):
        load_reference_catalog(root)


def test_duplicate_layer_ids_fail(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "geospatial_layers.json",
        {
            "version": 1,
            "layers": [
                {
                    "layerId": "layer-1",
                    "displayName": "Layer 1",
                    "group": "common",
                    "provider": "gibs",
                    "aliases": [],
                    "keywords": [],
                },
                {
                    "layerId": "layer-1",
                    "displayName": "Layer 1 duplicate",
                    "group": "common",
                    "provider": "gibs",
                    "aliases": [],
                    "keywords": [],
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="Duplicate geospatial layer ID"):
        load_reference_catalog(root)


def test_gibs_layer_defaults_require_a_populated_value(tmp_path: Path) -> None:
    root = _build_reference_root(tmp_path)
    _write_json(
        root / "reference" / "gibs_layer_defaults.json",
        {
            "version": 1,
            "layerDefaults": [
                {
                    "layerId": "layer-1",
                    "nativeResolutionM": None,
                    "dateFallbackDays": None,
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="must define at least one value"):
        load_reference_catalog(root)


def test_macau_alias_resolves_to_mo() -> None:
    catalog = load_reference_catalog(get_catalog_root())
    aliases = {entry.alias: entry.iso2 for entry in catalog.country_aliases}

    assert aliases["Macau"] == "MO"
