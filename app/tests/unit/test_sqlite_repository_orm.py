from __future__ import annotations

from pathlib import Path

from server.configurations import DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.database.initializer import initialize_database
from server.common.constants import REFERENCE_GEOSPATIAL_LAYERS_TABLE_NAME

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
    initialize_database(repository)

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
def test_upsert_handles_canonical_conversation_key(tmp_path) -> None:
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
    initialize_database(repository)

    repository.upsert_into_database(
        [
            {
                "id": "conv_test",
                "title": "Current conversation",
            }
        ],
        "conversations",
    )

    rows = repository.load_from_database("conversations")
    assert repository.count_rows("conversations") == 1
    assert len(rows) == 1
    assert rows[0]["id"] == "conv_test"
    assert rows[0]["title"] == "Current conversation"

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
