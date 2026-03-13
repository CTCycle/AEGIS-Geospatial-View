from __future__ import annotations

from typing import Any

import sqlalchemy
from sqlalchemy import delete, func, select
from sqlalchemy.sql.elements import TextClause


# -----------------------------------------------------------------------------
def build_delete_all_rows_statement(table: Any) -> Any:
    return delete(table)


# -----------------------------------------------------------------------------
def build_count_rows_statement(table: Any) -> Any:
    return select(func.count()).select_from(table)


# -----------------------------------------------------------------------------
def build_postgres_database_exists_statement() -> TextClause:
    return sqlalchemy.text("SELECT 1 FROM pg_database WHERE datname=:name")


# -----------------------------------------------------------------------------
def build_postgres_create_database_statement(database_name: str) -> TextClause:
    safe_database = database_name.replace('"', '""')
    return sqlalchemy.text(
        f'CREATE DATABASE "{safe_database}" WITH ENCODING \'UTF8\' TEMPLATE template0'
    )
