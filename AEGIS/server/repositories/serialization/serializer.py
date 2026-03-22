from __future__ import annotations

from math import isnan
from typing import Any

from AEGIS.server.repositories.database.backend import database
from AEGIS.server.utils.constants import (
    GEONAMES_COLUMNS,
    GEONAMES_TABLE,
    GIBS_LAYER_COLUMNS,
    GIBS_LAYERS_TABLE,
    SEARCH_SESSION_COLUMNS,
    SEARCH_SESSIONS_TABLE,
)


###############################################################################
class DataSerializer:
    def __init__(self) -> None:
        pass

    # -------------------------------------------------------------------------
    def normalize_value(self, value: Any) -> Any:
        if isinstance(value, float) and isnan(value):
            return None
        return value

    # -------------------------------------------------------------------------
    def normalize_records(
        self, records: list[dict[str, Any]], columns: list[str]
    ) -> list[dict[str, Any]]:
        normalized_records: list[dict[str, Any]] = []
        for record in records:
            normalized_records.append(
                {
                    column: self.normalize_value(record.get(column))
                    for column in columns
                    if column in record
                }
            )
        return normalized_records

    # -----------------------------------------------------------------------------
    def upsert_geonames_records(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        normalized_records = self.normalize_records(records, GEONAMES_COLUMNS)
        database.upsert_into_database(normalized_records, GEONAMES_TABLE)

    # -----------------------------------------------------------------------------
    def upsert_gibs_layers(self, layers: list[dict[str, Any]]) -> None:
        if not layers:
            return
        normalized_records = self.normalize_records(layers, GIBS_LAYER_COLUMNS)
        database.upsert_into_database(normalized_records, GIBS_LAYERS_TABLE)

    # -----------------------------------------------------------------------------
    def insert_search_session(self, session: dict[str, Any]) -> None:
        if not session:
            return
        normalized_records = self.normalize_records([session], SEARCH_SESSION_COLUMNS)
        database.upsert_into_database(normalized_records, SEARCH_SESSIONS_TABLE)

    # -----------------------------------------------------------------------------
    def load_table(self, table_name: str) -> list[dict[str, Any]]:
        return database.load_from_database(table_name)

    # -----------------------------------------------------------------------------
    def load_table_records(self, table_name: str) -> dict[str, Any]:
        rows = self.load_table(table_name)
        columns = database.list_columns(table_name)
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "column_count": len(columns),
        }

    # -----------------------------------------------------------------------------
    def get_table_stats(self, table_name: str) -> dict[str, int]:
        column_count = len(database.list_columns(table_name))
        row_count = database.count_rows(table_name)
        return {
            "row_count": row_count,
            "column_count": column_count,
        }
