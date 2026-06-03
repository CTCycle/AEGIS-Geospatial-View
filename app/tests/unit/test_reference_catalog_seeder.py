from __future__ import annotations

from pathlib import Path

from server.configurations import DatabaseSettings
from server.repositories.database.initializer import initialize_database
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas import (
    ReferenceCountryAliasRecord,
    ReferenceCountryRecord,
    ReferenceGeospatialLayerAliasRecord,
    ReferenceGeospatialLayerKeywordRecord,
    ReferenceGeospatialLayerRecord,
    ReferenceGibsLayerDefaultRecord,
    ReferenceGibsTileMatrixSetRecord,
)
from server.repositories.catalog.reference_seeder import ReferenceCatalogSeeder


def _build_database(tmp_path: Path) -> SQLiteRepository:
    repository = SQLiteRepository(
        DatabaseSettings(
            database_path=str(tmp_path / "database.db"),
            embedded_database=True,
            engine=None,
            host=None,
            port=None,
            database_name=None,
            username=None,
            password=None,
            ssl=False,
            ssl_ca=None,
            connect_timeout=10,
            insert_batch_size=100,
        )
    )
    initialize_database(repository)
    return repository


def test_fresh_sqlite_database_creates_reference_tables(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)

    assert repository.count_records(ReferenceCountryRecord) == 0
    assert repository.count_records(ReferenceGeospatialLayerRecord) == 0
    assert repository.count_records(ReferenceGibsTileMatrixSetRecord) == 0
    assert repository.count_records(ReferenceGibsLayerDefaultRecord) == 0


def test_first_seed_inserts_all_reference_rows(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)

    result = ReferenceCatalogSeeder(repository).seed_if_needed()

    assert result.countries_seeded is True
    assert result.geospatial_layers_seeded is True
    assert result.gibs_tile_matrix_sets_seeded is True
    assert result.gibs_layer_defaults_seeded is True
    assert repository.count_records(ReferenceCountryRecord) > 0
    assert repository.count_records(ReferenceCountryAliasRecord) > 0
    assert repository.count_records(ReferenceGeospatialLayerRecord) > 0
    assert repository.count_records(ReferenceGeospatialLayerAliasRecord) > 0
    assert repository.count_records(ReferenceGeospatialLayerKeywordRecord) > 0
    assert repository.count_records(ReferenceGibsTileMatrixSetRecord) > 0
    assert repository.count_records(ReferenceGibsLayerDefaultRecord) > 0


def test_second_seed_does_not_insert_duplicates(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)
    seeder = ReferenceCatalogSeeder(repository)

    seeder.seed_if_needed()
    first_counts = {
        "countries": repository.count_records(ReferenceCountryRecord),
        "aliases": repository.count_records(ReferenceCountryAliasRecord),
        "layers": repository.count_records(ReferenceGeospatialLayerRecord),
        "layer_aliases": repository.count_records(ReferenceGeospatialLayerAliasRecord),
        "layer_keywords": repository.count_records(
            ReferenceGeospatialLayerKeywordRecord
        ),
        "tile_matrix_sets": repository.count_records(ReferenceGibsTileMatrixSetRecord),
        "layer_defaults": repository.count_records(ReferenceGibsLayerDefaultRecord),
    }

    result = seeder.seed_if_needed()

    assert result.countries_seeded is False
    assert result.geospatial_layers_seeded is False
    assert result.gibs_tile_matrix_sets_seeded is False
    assert result.gibs_layer_defaults_seeded is False
    assert first_counts == {
        "countries": repository.count_records(ReferenceCountryRecord),
        "aliases": repository.count_records(ReferenceCountryAliasRecord),
        "layers": repository.count_records(ReferenceGeospatialLayerRecord),
        "layer_aliases": repository.count_records(ReferenceGeospatialLayerAliasRecord),
        "layer_keywords": repository.count_records(
            ReferenceGeospatialLayerKeywordRecord
        ),
        "tile_matrix_sets": repository.count_records(ReferenceGibsTileMatrixSetRecord),
        "layer_defaults": repository.count_records(ReferenceGibsLayerDefaultRecord),
    }


def test_country_seeding_is_skipped_when_reference_countries_populated(
    tmp_path: Path,
) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(ReferenceCountryRecord(iso2="ZZ", name="Seeded Country"))
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed()

    assert result.countries_seeded is False


def test_layer_seeding_is_skipped_when_reference_layers_populated(
    tmp_path: Path,
) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(
            ReferenceGeospatialLayerRecord(
                layer_id="seeded-layer",
                display_name="Seeded Layer",
                group="common",
                provider="gibs",
            )
        )
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed()

    assert result.geospatial_layers_seeded is False


def test_tile_matrix_seeding_is_skipped_when_table_populated(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(
            ReferenceGibsTileMatrixSetRecord(
                tile_matrix_set_id="seeded",
                meters_per_pixel=1.0,
            )
        )
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed()

    assert result.gibs_tile_matrix_sets_seeded is False


def test_layer_default_seeding_is_skipped_when_table_populated(tmp_path: Path) -> None:
    repository = _build_database(tmp_path)
    with repository.session() as session:
        session.add(
            ReferenceGibsLayerDefaultRecord(
                layer_id="seeded",
                native_resolution_m=1.0,
                date_fallback_days=None,
            )
        )
        session.commit()

    result = ReferenceCatalogSeeder(repository).seed_if_needed()

    assert result.gibs_layer_defaults_seeded is False
