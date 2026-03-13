from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


# -----------------------------------------------------------------------------
def build_postgres_upsert_statement(
    table: Any, batch: list[dict[str, Any]], unique_columns: Sequence[str]
) -> Any:
    statement = postgres_insert(table).values(batch)
    update_columns = {
        column: getattr(statement.excluded, column)  # type: ignore[attr-defined]
        for column in batch[0]
        if column not in unique_columns
    }
    return statement.on_conflict_do_update(
        index_elements=list(unique_columns), set_=update_columns
    )


# -----------------------------------------------------------------------------
def build_sqlite_upsert_statement(
    table: Any, batch: list[dict[str, Any]], unique_columns: Sequence[str]
) -> Any:
    statement = sqlite_insert(table).values(batch)
    update_columns = {
        column: getattr(statement.excluded, column)  # type: ignore[attr-defined]
        for column in batch[0]
        if column not in unique_columns
    }
    return statement.on_conflict_do_update(
        index_elements=list(unique_columns), set_=update_columns
    )
