from __future__ import annotations

from pathlib import Path

from server.configurations import DatabaseSettings
from server.repositories.database.initializer import initialize_database
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.catalog.reference_repository import ReferenceCatalogRepository
from server.services.catalog.startup import seed_reference_catalog

###############################################################################
def _seeded_repository(tmp_path: Path) -> SQLiteRepository:
    repository = SQLiteRepository(
        DatabaseSettings(
            database_path=str(tmp_path / "database.db"),
        )
    )
    initialize_database(
        repository,
        on_ready=lambda: seed_reference_catalog(repository),
    )
    return repository

###############################################################################
def test_gibs_reference_maps_load_from_reference_tables(tmp_path: Path) -> None:
    repository = _seeded_repository(tmp_path)
    reference_repository = ReferenceCatalogRepository(repository)

    native_resolution_map = reference_repository.load_gibs_layer_native_resolution_map()
    date_fallback_map = reference_repository.load_gibs_layer_date_fallback_days_map()
    tile_matrix_map = reference_repository.load_gibs_tile_matrix_resolution_map()

    assert native_resolution_map["VIIRS_SNPP_CorrectedReflectance_TrueColor"] == 375.0
    assert date_fallback_map["MODIS_Combined_Thermal_Anomalies_All"] == 3
    assert tile_matrix_map["250m"] == 250.0
