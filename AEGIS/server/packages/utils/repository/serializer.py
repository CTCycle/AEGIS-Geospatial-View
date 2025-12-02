from __future__ import annotations

from typing import Any

import pandas as pd

from AEGIS.server.packages.constants import (
    GEONAMES_COLUMNS,
    GIBS_LAYER_COLUMNS,
)
from AEGIS.server.packages.database.database import database


###############################################################################
class DataSerializer:
    def __init__(self) -> None:
        pass

    # -----------------------------------------------------------------------------
    def upsert_geonames_records(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        frame = pd.DataFrame.from_records(records)
        frame = frame.reindex(columns=GEONAMES_COLUMNS)
        frame = frame.where(pd.notnull(frame), None)
        database.upsert_into_database(frame, "GEONAMES")

    # -----------------------------------------------------------------------------
    def upsert_gibs_layers(self, layers: list[dict[str, Any]]) -> None:
        if not layers:
            return
        frame = pd.DataFrame.from_records(layers)
        frame = frame.reindex(columns=GIBS_LAYER_COLUMNS)
        frame = frame.where(pd.notnull(frame), None)
        database.upsert_into_database(frame, "GIBS_LAYERS")
