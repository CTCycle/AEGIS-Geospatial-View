from __future__ import annotations

from server.configurations import DatabaseSettings
from server.repositories.database.initializer import initialize_database
from server.repositories.schemas import (
    ReferenceCountryAliasRecord,
    ReferenceCountryRecord,
    ReferenceGeospatialLayerAliasRecord,
    ReferenceGeospatialLayerKeywordRecord,
    ReferenceGeospatialLayerRecord,
    ReferenceGibsLayerDefaultRecord,
    ReferenceGibsTileMatrixSetRecord,
)


def test_initialize_database_ensures_sqlite_schema(monkeypatch, tmp_path) -> None:
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
        insert_batch_size=100,
    )
    created: list[object] = []

    class _Repository:
        def __init__(self, passed_settings: DatabaseSettings) -> None:
            self.engine = object()
            self.db_path = passed_settings.database_path
            created.append(self.engine)

    monkeypatch.setattr(
        "server.repositories.database.initializer.SQLiteRepository",
        _Repository,
    )
    calls: list[object] = []
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: calls.append(engine),
    )

    initialize_database(settings)

    assert calls == created


def test_initialize_database_uses_passed_database_settings(
    monkeypatch, tmp_path
) -> None:
    settings = DatabaseSettings(
        database_path=str(tmp_path / "custom.db"),
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
        insert_batch_size=250,
    )
    received: list[DatabaseSettings] = []

    class _Repository:
        def __init__(self, passed_settings: DatabaseSettings) -> None:
            received.append(passed_settings)
            self.engine = object()
            self.db_path = passed_settings.database_path

    monkeypatch.setattr(
        "server.repositories.database.initializer.SQLiteRepository",
        _Repository,
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: None,
    )

    initialize_database(settings)

    assert received == [settings]


def test_initialize_database_defaults_to_server_settings(monkeypatch, tmp_path) -> None:
    settings = DatabaseSettings(
        database_path=str(tmp_path / "default.db"),
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
        insert_batch_size=400,
    )
    received: list[DatabaseSettings] = []

    class _Repository:
        def __init__(self, passed_settings: DatabaseSettings) -> None:
            received.append(passed_settings)
            self.engine = object()
            self.db_path = passed_settings.database_path

    monkeypatch.setattr(
        "server.repositories.database.initializer.get_server_settings",
        lambda: type("Settings", (), {"database": settings})(),
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.SQLiteRepository",
        _Repository,
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: None,
    )

    initialize_database()

    assert received == [settings]


def test_initialize_database_ensures_postgres_schema_when_external_mode(
    monkeypatch, tmp_path
) -> None:
    settings = DatabaseSettings(
        database_path=str(tmp_path / "database.db"),
        embedded_database=False,
        engine="postgresql+psycopg",
        host="localhost",
        port=5432,
        database_name="aegis",
        username="postgres",
        password="postgres",
        ssl=False,
        ssl_ca=None,
        connect_timeout=10,
        insert_batch_size=100,
    )

    monkeypatch.setattr(
        "server.repositories.database.initializer.PostgresRepository",
        lambda passed_settings: type(
            "Repository",
            (),
            {"engine": object(), "db_path": passed_settings.database_path},
        )(),
    )
    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        lambda engine: None,
    )

    initialize_database(settings)

    assert "server.repositories.database.postgres" in __import__("sys").modules


def test_initialize_database_creates_reference_tables(monkeypatch) -> None:
    created_tables: list[str] = []

    class _Engine:
        pass

    class _Database:
        engine = _Engine()

    def _capture_create_all(engine: object) -> None:
        del engine
        created_tables.extend(
            sorted(
                [
                    ReferenceCountryRecord.__tablename__,
                    ReferenceCountryAliasRecord.__tablename__,
                    ReferenceGeospatialLayerRecord.__tablename__,
                    ReferenceGeospatialLayerAliasRecord.__tablename__,
                    ReferenceGeospatialLayerKeywordRecord.__tablename__,
                    ReferenceGibsTileMatrixSetRecord.__tablename__,
                    ReferenceGibsLayerDefaultRecord.__tablename__,
                ]
            )
        )

    monkeypatch.setattr(
        "server.repositories.database.initializer.Base.metadata.create_all",
        _capture_create_all,
    )

    initialize_database(_Database())

    assert created_tables == sorted(created_tables)


def test_startup_path_seeds_reference_catalog_after_schema_creation(
    monkeypatch,
) -> None:
    call_order: list[str] = []

    class _Backend:
        engine = object()

    class _Database:
        backend = _Backend()

    monkeypatch.setattr(
        "server.app.get_server_settings",
        lambda: type(
            "Settings",
            (),
            {
                "database": object(),
                "jobs": type(
                    "JobsSettings",
                    (),
                    {
                        "backend": "in_process",
                        "require_durable_backend": False,
                    },
                )(),
            },
        )(),
    )
    monkeypatch.setattr("server.app.get_database", lambda: _Database())
    monkeypatch.setattr(
        "server.app.initialize_database",
        lambda database: call_order.append("initialize"),
    )
    monkeypatch.setattr(
        "server.app.seed_reference_catalog",
        lambda database: call_order.append("seed"),
    )
    monkeypatch.setattr(
        "server.app.build_search_runtime",
        lambda: type(
            "SearchRuntime",
            (),
            {
                "search_orchestrator": object(),
                "job_manager": __import__(
                    "server.services.jobs",
                    fromlist=["InProcessJobBackend"],
                ).InProcessJobBackend(),
            },
        )(),
    )
    monkeypatch.setattr(
        "server.app.build_chat_runtime",
        lambda _search_orchestrator: type(
            "ChatRuntime",
            (),
            {
                "settings_service": type(
                    "SettingsService", (), {"get_settings": staticmethod(lambda: None)}
                )(),
                "maintenance_service": object(),
            },
        )(),
    )
    monkeypatch.setattr(
        "server.app.build_geospatial_runtime",
        lambda: type(
            "GeospatialRuntime",
            (),
            {"api_service": object()},
        )(),
    )
    monkeypatch.setattr("server.app.run_startup_validations", lambda settings: None)

    app_module = __import__("server.app", fromlist=["app_lifespan"])

    async def _exercise() -> None:
        async with app_module.app_lifespan(
            type("Application", (), {"state": type("State", (), {})()})()
        ):
            pass

    __import__("asyncio").run(_exercise())

    assert call_order[:2] == ["initialize", "seed"]
