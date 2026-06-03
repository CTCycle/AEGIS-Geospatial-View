from __future__ import annotations

from typing import Any, Protocol

from server.repositories.schemas import Base


class DatabaseBackend(Protocol):
    db_path: str | None
    engine: Any
    session: Any

    def load_from_database(self, table_name: str) -> list[dict[str, Any]]: ...

    def upsert_into_database(
        self, records: list[dict[str, Any]], table_name: str
    ) -> None: ...

    def count_rows(self, table_name: str) -> int: ...

    def count_records(self, model: type[Base]) -> int: ...

    def list_columns(self, table_name: str) -> list[str]: ...
