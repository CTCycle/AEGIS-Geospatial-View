from __future__ import annotations

import pandas as pd

from AEGIS.server.repositories.database.backend import database


# -----------------------------------------------------------------------------
def upsert_table_frame(frame: pd.DataFrame, table_name: str) -> None:
    database.upsert_into_database(frame, table_name)


# -----------------------------------------------------------------------------
def load_table_frame(table_name: str) -> pd.DataFrame:
    return database.load_from_database(table_name)


# -----------------------------------------------------------------------------
def count_table_rows(table_name: str) -> int:
    return database.count_rows(table_name)
