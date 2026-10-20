from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from alembic.script import ScriptDirectory

from server.api.settings import router as settings_router
from server.common.paths import ROOT_DIR
from server.configurations.database_configuration import DatabaseConfiguration
from server.configurations.settings import DatabaseSettings
from server.repositories.schemas import Base
from server.services.database_runtime import (
    DatabaseConnectionError,
    DatabaseRuntimeBusyError,
    DatabaseRuntimeGateMiddleware,
    DatabaseRuntimeManager,
    DatabaseRuntimeSwitchError,
    inspect_database_configuration,
)


def _manager(
    monkeypatch,
    tmp_path: Path,
    *,
    busy_reasons=None,
    activation_error: bool = False,
) -> tuple[DatabaseRuntimeManager, DatabaseConfiguration, list[Any], list[Any]]:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path / "config-root"))
    previous_configuration = DatabaseConfiguration(
        database_path=str(tmp_path / "active.sqlite")
    )
    previous_runtime = SimpleNamespace(
        database=SimpleNamespace(
            settings=DatabaseSettings(
                database_path=previous_configuration.database_path
            )
        ),
        name="previous",
    )
    published: list[Any] = []
    shutdown: list[Any] = []

    def build_candidate(settings: DatabaseSettings) -> Any:
        return SimpleNamespace(
            database=SimpleNamespace(settings=settings), name="candidate"
        )

    def publish_runtime(runtime: Any) -> None:
        published.append(runtime)

    async def activate_runtime(runtime: Any) -> None:
        if activation_error:
            raise RuntimeError("controlled activation failure")

    async def shutdown_runtime(runtime: Any) -> None:
        shutdown.append(runtime)

    manager = DatabaseRuntimeManager(
        configuration=previous_configuration,
        runtime_bundle=previous_runtime,
        build_candidate=build_candidate,
        publish_runtime=publish_runtime,
        activate_runtime=activate_runtime,
        shutdown_runtime=shutdown_runtime,
        busy_reasons=busy_reasons or (lambda _: []),
    )
    return manager, previous_configuration, published, shutdown


def test_database_target_test_reports_empty_and_rejects_corrupt_files(
    tmp_path: Path,
) -> None:
    empty = DatabaseConfiguration(database_path=str(tmp_path / "new.sqlite"))

    result = inspect_database_configuration(empty)

    assert result.schema_status == "empty"
    assert not Path(empty.database_path).exists()

    corrupt_path = tmp_path / "corrupt.sqlite"
    corrupt_path.write_bytes(b"not sqlite")
    with pytest.raises(DatabaseConnectionError, match="could not open or read"):
        inspect_database_configuration(
            DatabaseConfiguration(database_path=str(corrupt_path))
        )


@pytest.mark.asyncio
async def test_database_switch_persists_target_and_shuts_down_previous_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manager, previous, published, shutdown = _manager(monkeypatch, tmp_path)
    target = DatabaseConfiguration(database_path=str(tmp_path / "next.sqlite"))

    response = await manager.switch_database(target)

    assert response.database_path == target.database_path
    assert manager.configuration == target
    assert published[-1].name == "candidate"
    assert shutdown[0].name == "previous"


@pytest.mark.asyncio
async def test_failed_activation_rolls_runtime_and_file_configuration_back(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manager, previous, published, shutdown = _manager(
        monkeypatch, tmp_path, activation_error=True
    )
    target = DatabaseConfiguration(database_path=str(tmp_path / "rejected.sqlite"))

    with pytest.raises(
        DatabaseRuntimeSwitchError, match="previous database remains active"
    ):
        await manager.switch_database(target)

    assert manager.configuration == previous
    assert [runtime.name for runtime in published] == ["candidate", "previous"]
    assert shutdown[0].name == "candidate"


@pytest.mark.asyncio
async def test_database_switch_is_rejected_while_requests_or_jobs_are_active(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manager, previous, published, shutdown = _manager(
        monkeypatch,
        tmp_path,
        busy_reasons=lambda _: ["background jobs"],
    )
    target = DatabaseConfiguration(database_path=str(tmp_path / "busy.sqlite"))

    with pytest.raises(DatabaseRuntimeBusyError, match="background jobs"):
        await manager.switch_database(target)

    assert manager.configuration == previous
    assert published == []
    assert shutdown[0].name == "candidate"


@pytest.mark.asyncio
async def test_database_switch_is_rejected_when_current_database_state_cannot_be_checked(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def unavailable_database(_: Any) -> list[str]:
        raise RuntimeError("controlled database read failure")

    manager, previous, published, shutdown = _manager(
        monkeypatch,
        tmp_path,
        busy_reasons=unavailable_database,
    )
    target = DatabaseConfiguration(database_path=str(tmp_path / "target.sqlite"))

    with pytest.raises(DatabaseRuntimeSwitchError, match="Restore access to it"):
        await manager.switch_database(target)

    assert manager.configuration == previous
    assert published == []
    assert shutdown[0].name == "candidate"


@pytest.mark.asyncio
async def test_database_switch_is_rejected_during_an_inflight_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manager, previous, published, shutdown = _manager(monkeypatch, tmp_path)
    target = DatabaseConfiguration(database_path=str(tmp_path / "request-busy.sqlite"))
    assert manager.enter_request()

    try:
        with pytest.raises(DatabaseRuntimeBusyError, match="requests are in flight"):
            await manager.switch_database(target)
    finally:
        manager.leave_request()

    assert manager.configuration == previous
    assert published == []
    assert shutdown[0].name == "candidate"


def test_database_settings_api_reports_connection_and_busy_switch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manager, previous, _, _ = _manager(
        monkeypatch,
        tmp_path,
        busy_reasons=lambda _: ["background jobs"],
    )
    application = FastAPI()
    application.add_middleware(
        DatabaseRuntimeGateMiddleware,
        state=application.state,
    )
    application.include_router(settings_router, prefix="/api")
    application.state.database_runtime_manager = manager
    client = TestClient(application)
    target = {
        "backend": "sqlite",
        "database_path": str(tmp_path / "target.sqlite"),
        "sqlite_lock_timeout_seconds": 60,
    }

    tested = client.post("/api/settings/database/test", json=target)
    switched = client.put("/api/settings/database", json=target)
    current = client.get("/api/settings/database")

    assert tested.status_code == 200
    assert tested.json()["schema_status"] == "empty"
    assert switched.status_code == 409
    assert "background jobs" in switched.json()["detail"]
    assert current.status_code == 200
    assert current.json()["database_path"] == previous.database_path


def test_unversioned_populated_database_is_not_adopted(tmp_path: Path) -> None:
    database_path = tmp_path / "unversioned.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")

    with pytest.raises(DatabaseConnectionError, match="no Alembic revision"):
        inspect_database_configuration(
            DatabaseConfiguration(database_path=str(database_path))
        )


def test_current_revision_with_missing_application_tables_is_rejected(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "incomplete.sqlite"
    migration_config = Config(str(ROOT_DIR / "app" / "server" / "alembic.ini"))
    revision = ScriptDirectory.from_config(migration_config).get_heads()[0]
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)", (revision,)
        )

    assert Base.metadata.tables
    with pytest.raises(
        DatabaseConnectionError, match="missing required application tables"
    ):
        inspect_database_configuration(
            DatabaseConfiguration(database_path=str(database_path))
        )
