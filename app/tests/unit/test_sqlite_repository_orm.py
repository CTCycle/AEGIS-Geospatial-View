from __future__ import annotations

from pathlib import Path

from server.configurations import DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.common.constants import (
    CHAT_SESSIONS_TABLE,
    REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME,
)


###############################################################################
def test_upsert_uses_orm_and_updates_existing_rows(tmp_path) -> None:
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
            insert_batch_size=1,
        )
    )
    repository.ensure_schema()

    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "display_name": "Original",
                "group": "test",
                "provider": "gibs",
            }
        ],
        REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME,
    )

    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "display_name": "Updated",
                "group": "test",
                "provider": "gibs",
            }
        ],
        REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME,
    )

    rows = repository.load_from_database(REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME)
    assert repository.count_rows(REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME) == 1
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Updated"


###############################################################################
def test_upsert_adds_new_rows_and_updates_existing_rows(tmp_path) -> None:
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
            insert_batch_size=2,
        )
    )
    repository.ensure_schema()

    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "display_name": "One",
                "group": "test",
                "provider": "gibs",
            }
        ],
        REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME,
    )
    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-1",
                "display_name": "One Updated",
                "group": "test",
                "provider": "gibs",
            }
        ],
        REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME,
    )
    repository.upsert_into_database(
        [
            {
                "layer_id": "layer-2",
                "display_name": "Two",
                "group": "test",
                "provider": "gibs",
            }
        ],
        REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME,
    )

    rows = repository.load_from_database(REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME)
    by_id = {row["layer_id"]: row for row in rows}
    assert repository.count_rows(REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME) == 2
    assert len(rows) == 2
    assert by_id["layer-1"]["display_name"] == "One Updated"
    assert by_id["layer-2"]["display_name"] == "Two"


###############################################################################
def test_upsert_omits_null_autoincrement_primary_key(tmp_path) -> None:
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
            insert_batch_size=2,
        )
    )
    repository.ensure_schema()

    repository.upsert_into_database(
        [
            {
                "id": None,
                "title": "Current session",
                "status": "active",
                "last_map_session_json": "{}",
            }
        ],
        CHAT_SESSIONS_TABLE,
    )

    rows = repository.load_from_database(CHAT_SESSIONS_TABLE)
    assert repository.count_rows(CHAT_SESSIONS_TABLE) == 1
    assert len(rows) == 1
    assert isinstance(rows[0]["id"], int)
    assert rows[0]["title"] == "Current session"
    assert rows[0]["status"] == "active"


###############################################################################
def test_repository_uses_database_path_from_settings(tmp_path) -> None:
    settings = DatabaseSettings(
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
        insert_batch_size=1000,
    )

    repository = SQLiteRepository(settings)

    assert repository.db_path == settings.database_path


###############################################################################
def test_repository_creates_parent_directory_for_database_path(tmp_path) -> None:
    database_path = tmp_path / "nested" / "data" / "database.db"
    settings = DatabaseSettings(
        database_path=str(database_path),
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
        insert_batch_size=1000,
    )

    SQLiteRepository(settings)

    assert Path(database_path.parent).is_dir()
