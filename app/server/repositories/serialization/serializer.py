from __future__ import annotations

from math import isnan
from typing import Any

from server.repositories.database.backend import get_database
from server.common.constants import (
    GIBS_LAYER_COLUMNS,
    GIBS_LAYERS_TABLE,
)


###############################################################################
class DataSerializer:
    def __init__(self) -> None:
        self.database = get_database()

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
    def upsert_gibs_layers(self, layers: list[dict[str, Any]]) -> None:
        if not layers:
            return
        normalized_records = self.normalize_records(layers, GIBS_LAYER_COLUMNS)
        self.database.upsert_into_database(normalized_records, GIBS_LAYERS_TABLE)

    # -----------------------------------------------------------------------------
    def load_table(self, table_name: str) -> list[dict[str, Any]]:
        return self.database.load_from_database(table_name)

    # -----------------------------------------------------------------------------
    def load_table_records(self, table_name: str) -> dict[str, Any]:
        rows = self.load_table(table_name)
        columns = self.database.list_columns(table_name)
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "column_count": len(columns),
        }

    # -----------------------------------------------------------------------------
    def get_table_stats(self, table_name: str) -> dict[str, int]:
        column_count = len(self.database.list_columns(table_name))
        row_count = self.database.count_rows(table_name)
        return {
            "row_count": row_count,
            "column_count": column_count,
        }
