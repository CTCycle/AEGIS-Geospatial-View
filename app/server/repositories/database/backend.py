from __future__ import annotations

from server.configurations import DatabaseSettings
from server.repositories.database.contracts import DatabaseBackend
from server.repositories.database.postgres import PostgresRepository
from server.repositories.database.sqlite import SQLiteRepository

###############################################################################
def build_database_backend(settings: DatabaseSettings) -> DatabaseBackend:
    if settings.embedded_database:
        return SQLiteRepository(settings)
    return PostgresRepository(settings)
