from __future__ import annotations

from server.configurations import DatabaseSettings
from server.repositories.database.initializer import initialize_database
###############################################################################
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

    ###############################################################################
    class _Repository:

        # -------------------------------------------------------------------------
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

    ###############################################################################
    class _Repository:

        # -------------------------------------------------------------------------
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


###############################################################################
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


def test_startup_path_seeds_reference_catalog_after_schema_creation(
    monkeypatch,
) -> None:
    call_order: list[str] = []

    ###############################################################################
    class _Backend:
        engine = object()

    ###############################################################################
    class _Database:
        backend = _Backend()

    monkeypatch.setattr(
        "server.app.get_server_settings",
        lambda: type(
            "Settings",
            (),
            {
                "database": object(),
                "jobs": type("JobsSettings", (), {"polling_interval": 1.0})(),
            },
        )(),
    )
    monkeypatch.setattr("server.app.get_database", lambda: _Database())
    monkeypatch.setattr(
        "server.app.initialize_database",
        lambda database: call_order.append("initialize"),
    )
    monkeypatch.setattr(
        "server.app.seed_credential_encryption_material",
        lambda: call_order.append("seed_credential_encryption_material"),
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
                "search_orchestrator": type(
                    "Orchestrator",
                    (),
                    {"execute": staticmethod(lambda payload: payload)},
                )(),
            },
        )(),
    )
    monkeypatch.setattr(
        "server.app.build_chat_runtime",
        lambda _search_orchestrator: type(
            "ChatRuntime",
            (),
            {
                "agent_orchestrator": object(),
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
    monkeypatch.setattr(
        "server.app.BackgroundJobService",
        lambda **kwargs: type(
            "JobService",
            (),
            {"start": staticmethod(lambda: None), "stop": staticmethod(lambda: None)},
        )(),
    )
    monkeypatch.setattr("server.app.ChatStreamingService", lambda orchestrator: object())
    monkeypatch.setattr("server.app.run_startup_validations", lambda: None)

    app_module = __import__("server.app", fromlist=["app_lifespan"])

    async def _exercise() -> None:
        async with app_module.app_lifespan(
            type("Application", (), {"state": type("State", (), {})()})()
        ):
            pass

    __import__("asyncio").run(_exercise())

    assert call_order[:3] == [
        "initialize",
        "seed_credential_encryption_material",
        "seed",
    ]
