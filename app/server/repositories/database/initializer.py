from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from server.common.logger import logger
from server.repositories.credential_material import seed_credential_encryption_material
from server.repositories.database.migration_runner import (
    MigrationResult,
    synchronize_database,
)
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.repositories.runtime_settings import RuntimeSettingsRepository

###############################################################################
def initialize_database(
    database: SQLiteRepository,
    *,
    on_ready: Callable[[], None] | None = None,
    legacy_settings_path: Path | None = None,
) -> MigrationResult:
    def seed_required_data() -> None:
        seed_credential_encryption_material(database)
        ModelSettingsRepository(database).seed_required()
        RuntimeSettingsRepository(database).seed_required(
            legacy_path=legacy_settings_path
        )
        if on_ready is not None:
            on_ready()

    result = synchronize_database(database, on_ready=seed_required_data)
    logger.info(
        "SQLite database is ready: fresh=%s, migrations_applied=%s",
        result.fresh_database,
        result.migrations_applied,
    )
    return result


###############################################################################
