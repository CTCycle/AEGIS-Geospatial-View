from __future__ import annotations

from datetime import UTC, datetime

from AEGIS.server.configurations.server import DatabaseSettings
from AEGIS.server.repositories.database.sqlite import SQLiteRepository
from AEGIS.server.utils.constants import GIBS_LAYERS_TABLE, SEARCH_SESSIONS_TABLE


def build_test_settings(insert_batch_size: int = 2) -> DatabaseSettings:
    return DatabaseSettings(
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
        insert_batch_size=insert_batch_size,
    )


def test_upsert_uses_orm_and_updates_existing_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "AEGIS.server.repositories.database.sqlite.RESOURCES_PATH", str(tmp_path)
    )
    repository = SQLiteRepository(build_test_settings(insert_batch_size=1))

    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "title": "Original",
                "abstract": "first",
                "projections": "[]",
                "source_urls": "[]",
                "tile_matrix_sets": "[]",
                "meters_per_pixel": "[]",
            }
        ],
        GIBS_LAYERS_TABLE,
    )

    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "title": "Updated",
                "abstract": "first",
                "projections": "[]",
                "source_urls": "[]",
                "tile_matrix_sets": "[]",
                "meters_per_pixel": "[]",
            }
        ],
        GIBS_LAYERS_TABLE,
    )

    rows = repository.load_from_database(GIBS_LAYERS_TABLE)
    assert repository.count_rows(GIBS_LAYERS_TABLE) == 1
    assert len(rows) == 1
    assert rows[0]["title"] == "Updated"


def test_upsert_adds_new_rows_and_updates_existing_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "AEGIS.server.repositories.database.sqlite.RESOURCES_PATH", str(tmp_path)
    )
    repository = SQLiteRepository(build_test_settings())

    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "title": "One",
            }
        ],
        GIBS_LAYERS_TABLE,
    )
    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "title": "One Updated",
            }
        ],
        GIBS_LAYERS_TABLE,
    )
    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-2",
                "title": "Two",
            }
        ],
        GIBS_LAYERS_TABLE,
    )

    rows = repository.load_from_database(GIBS_LAYERS_TABLE)
    by_id = {row["layer_id"]: row for row in rows}
    assert repository.count_rows(GIBS_LAYERS_TABLE) == 2
    assert len(rows) == 2
    assert by_id["layer-1"]["title"] == "One Updated"
    assert by_id["layer-2"]["title"] == "Two"


def test_upsert_omits_null_autoincrement_primary_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "AEGIS.server.repositories.database.sqlite.RESOURCES_PATH", str(tmp_path)
    )
    repository = SQLiteRepository(build_test_settings())

    repository.upsert_into_database(
        [
            {
                "id": None,
                "created_at": datetime.now(UTC),
                "user": "tester",
                "country": "IT",
                "city": "Rome",
                "address": "Via Roma",
                "coordinates": '{"longitude": 12.5, "latitude": 41.9}',
                "base_map": "OpenStreetMap",
                "geospatial_layers": '["Layer"]',
                "state": "success",
            }
        ],
        SEARCH_SESSIONS_TABLE,
    )

    rows = repository.load_from_database(SEARCH_SESSIONS_TABLE)
    assert repository.count_rows(SEARCH_SESSIONS_TABLE) == 1
    assert len(rows) == 1
    assert isinstance(rows[0]["id"], int)
