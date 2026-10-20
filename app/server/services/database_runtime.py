from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError

from server.common.paths import ROOT_DIR
from server.configurations import DatabaseSettings
from server.configurations.database_configuration import (
    DatabaseConfiguration,
    restore_database_configuration,
    save_database_configuration,
)
from server.contracts.database_settings import (
    DatabaseConnectionTestResponse,
    DatabaseSettingsResponse,
)
from server.repositories.schemas import Base

LOGGER = logging.getLogger(__name__)


class DatabaseConnectionError(RuntimeError):
    """Raised when a SQLite target cannot be safely opened or initialized."""


class DatabaseRuntimeBusyError(RuntimeError):
    """Raised when a runtime switch would interrupt active application work."""


class DatabaseRuntimeSwitchError(RuntimeError):
    """Raised when preparing or activating a replacement runtime fails."""


@dataclass(frozen=True)
class SQLiteTargetInspection:
    configuration: DatabaseConfiguration
    schema_status: str
    message: str


def inspect_database_configuration(
    configuration: DatabaseConfiguration,
) -> SQLiteTargetInspection:
    """Check the connection and schema without migrating or creating the target."""

    path = Path(configuration.database_path)
    if path.exists() and not path.is_file():
        raise DatabaseConnectionError("The SQLite database path is not a file.")
    if not path.exists():
        if path.parent.exists() and not path.parent.is_dir():
            raise DatabaseConnectionError(
                "The SQLite database parent is not a directory."
            )
        return SQLiteTargetInspection(
            configuration=configuration,
            schema_status="empty",
            message="The path is available; AEGIS will create and initialize the database when switched.",
        )

    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=2.0) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if quick_check is None or quick_check[0] != "ok":
                raise DatabaseConnectionError(
                    "SQLite reported a database integrity error."
                )
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            revisions = (
                tuple(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT version_num FROM alembic_version"
                    )
                )
                if "alembic_version" in tables
                else ()
            )
    except DatabaseConnectionError:
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise DatabaseConnectionError(
            "AEGIS could not open or read the SQLite database at the selected path."
        ) from exc

    application_tables = tables - {"alembic_version"}
    if not revisions and application_tables:
        raise DatabaseConnectionError(
            "The database contains tables but no Alembic revision; AEGIS will not adopt or overwrite it."
        )
    if not revisions:
        return SQLiteTargetInspection(
            configuration=configuration,
            schema_status="empty",
            message="The SQLite file is empty and can be initialized when switched.",
        )
    if len(revisions) != 1:
        raise DatabaseConnectionError(
            "The database has an unsupported Alembic revision state."
        )

    try:
        migration_config = Config(str(ROOT_DIR / "app" / "server" / "alembic.ini"))
        script = ScriptDirectory.from_config(migration_config)
        script.get_revision(revisions[0])
        latest = tuple(script.get_heads())
    except CommandError as exc:
        raise DatabaseConnectionError(
            f"The database references unknown Alembic revision {revisions[0]!r}."
        ) from exc
    except DatabaseConnectionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DatabaseConnectionError(
            "AEGIS could not validate the SQLite schema revision."
        ) from exc

    if revisions == latest:
        missing_tables = set(Base.metadata.tables) - tables
        if missing_tables:
            missing = ", ".join(sorted(missing_tables)[:5])
            raise DatabaseConnectionError(
                f"The database is missing required application tables: {missing}."
            )
        return SQLiteTargetInspection(
            configuration=configuration,
            schema_status="ready",
            message="The SQLite connection and schema are ready.",
        )
    return SQLiteTargetInspection(
        configuration=configuration,
        schema_status="upgradable",
        message="The SQLite connection is healthy; pending application migrations will run when switched.",
    )


def database_test_response(
    configuration: DatabaseConfiguration,
) -> DatabaseConnectionTestResponse:
    result = inspect_database_configuration(configuration)
    return DatabaseConnectionTestResponse(
        ok=True,
        backend="sqlite",
        database_path=result.configuration.database_path,
        schema_status=result.schema_status,  # type: ignore[arg-type]
        message=result.message,
    )


def database_settings_response(
    configuration: DatabaseConfiguration,
) -> DatabaseSettingsResponse:
    return DatabaseSettingsResponse(
        backend=configuration.backend,
        database_path=configuration.database_path,
        sqlite_lock_timeout_seconds=configuration.sqlite_lock_timeout_seconds,
        active=True,
    )


class DatabaseRuntimeManager:
    """Coordinates connection admission and safe, process-local runtime swaps."""

    def __init__(
        self,
        *,
        configuration: DatabaseConfiguration,
        runtime_bundle: Any,
        build_candidate: Callable[[DatabaseSettings], Any],
        publish_runtime: Callable[[Any], None],
        activate_runtime: Callable[[Any], Awaitable[None]],
        shutdown_runtime: Callable[[Any], Awaitable[None]],
        busy_reasons: Callable[[Any], list[str]],
    ) -> None:
        self._configuration = configuration
        self._runtime_bundle = runtime_bundle
        self._build_candidate = build_candidate
        self._publish_runtime = publish_runtime
        self._activate_runtime = activate_runtime
        self._shutdown_runtime = shutdown_runtime
        self._busy_reasons = busy_reasons
        self._lock = threading.Lock()
        self._active_requests = 0
        self._switching = False

    @property
    def configuration(self) -> DatabaseConfiguration:
        with self._lock:
            return self._configuration

    def enter_request(self) -> bool:
        with self._lock:
            if self._switching:
                return False
            self._active_requests += 1
            return True

    def leave_request(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    async def test_connection(
        self, configuration: DatabaseConfiguration
    ) -> DatabaseConnectionTestResponse:
        return await asyncio.to_thread(database_test_response, configuration)

    async def switch_database(
        self, configuration: DatabaseConfiguration
    ) -> DatabaseSettingsResponse:
        target = DatabaseConfiguration.model_validate(configuration.model_dump())
        await self.test_connection(target)
        current = self.configuration
        if target.database_path == current.database_path:
            if (
                target.sqlite_lock_timeout_seconds
                != current.sqlite_lock_timeout_seconds
            ):
                with self._lock:
                    if self._switching or self._active_requests:
                        raise DatabaseRuntimeBusyError(
                            "Database settings cannot be changed while requests are in flight."
                        )
                    self._switching = True
                try:
                    save_database_configuration(target)
                    with self._lock:
                        self._configuration = target
                    self._runtime_bundle.database.settings = DatabaseSettings(
                        database_path=target.database_path,
                        sqlite_lock_timeout_seconds=target.sqlite_lock_timeout_seconds,
                    )
                finally:
                    self._finish_switch()
            return database_settings_response(target)

        candidate_settings = DatabaseSettings(
            database_path=target.database_path,
            sqlite_lock_timeout_seconds=target.sqlite_lock_timeout_seconds,
        )
        try:
            candidate = await asyncio.to_thread(
                self._build_candidate, candidate_settings
            )
        except Exception as exc:
            raise DatabaseRuntimeSwitchError(
                "AEGIS could not initialize and validate the target database. The active database is unchanged."
            ) from exc

        owns_switch_gate = False
        try:
            self._begin_switch()
            owns_switch_gate = True
            try:
                busy = await asyncio.to_thread(self._busy_reasons, self._runtime_bundle)
            except Exception as exc:
                raise DatabaseRuntimeSwitchError(
                    "AEGIS could not verify the active database is idle. Restore access to it before switching."
                ) from exc
            if busy:
                raise DatabaseRuntimeBusyError(
                    "Switching is unavailable while " + ", ".join(busy) + " are active."
                )

            previous_configuration = self._configuration
            previous_runtime = self._runtime_bundle
            save_database_configuration(target)
            try:
                self._publish_runtime(candidate)
                await self._activate_runtime(candidate)
                with self._lock:
                    self._configuration = target
                    self._runtime_bundle = candidate
            except Exception as activation_error:
                self._publish_runtime(previous_runtime)
                with self._lock:
                    self._configuration = previous_configuration
                    self._runtime_bundle = previous_runtime
                restore_database_configuration(previous_configuration)
                raise DatabaseRuntimeSwitchError(
                    "AEGIS could not activate the target database. The previous database remains active."
                ) from activation_error

            try:
                await self._shutdown_runtime(previous_runtime)
            except Exception:  # noqa: BLE001
                LOGGER.exception(
                    "The previous database runtime did not shut down cleanly after a successful switch."
                )
            return database_settings_response(target)
        except DatabaseRuntimeBusyError:
            await self._shutdown_runtime(candidate)
            raise
        except DatabaseRuntimeSwitchError:
            await self._shutdown_runtime(candidate)
            raise
        except Exception as exc:
            await self._shutdown_runtime(candidate)
            raise DatabaseRuntimeSwitchError(
                "AEGIS could not switch databases. The previous database remains active."
            ) from exc
        finally:
            if owns_switch_gate:
                self._finish_switch()

    def _begin_switch(self) -> None:
        with self._lock:
            if self._switching:
                raise DatabaseRuntimeBusyError(
                    "Another database switch is already in progress."
                )
            if self._active_requests:
                raise DatabaseRuntimeBusyError(
                    "Database switching is unavailable while application requests are in flight."
                )
            self._switching = True

    def _finish_switch(self) -> None:
        with self._lock:
            self._switching = False


class DatabaseRuntimeGateMiddleware:
    """Counts complete HTTP/WebSocket lifetimes and pauses new work during swaps."""

    def __init__(self, app: Any, *, state: Any) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        kind = scope.get("type")
        path = str(scope.get("path", ""))
        if kind not in {"http", "websocket"} or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        if kind == "http" and (
            (path == "/api/settings/database" and method == "PUT")
            or (path == "/api/settings/database/test" and method == "POST")
        ):
            await self.app(scope, receive, send)
            return

        manager = getattr(self.state, "database_runtime_manager", None)
        if not isinstance(manager, DatabaseRuntimeManager) or manager.enter_request():
            try:
                await self.app(scope, receive, send)
            finally:
                if isinstance(manager, DatabaseRuntimeManager):
                    manager.leave_request()
            return

        if kind == "websocket":
            await send(
                {
                    "type": "websocket.close",
                    "code": 1013,
                    "reason": "database_switching",
                }
            )
            return

        body = json.dumps(
            {"detail": "Database switching is in progress; retry the request."}
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
