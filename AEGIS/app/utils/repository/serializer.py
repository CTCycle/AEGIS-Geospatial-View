from __future__ import annotations

from typing import Any

import pandas as pd

from AEGIS.app.utils.repository.database import database


# [DATA SERIALIZATION]
###############################################################################
GEONAMES_COLUMNS = [
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "country_code",
    "cc2",
    "admin1_code",
    "admin2_code",
    "admin3_code",
    "admin4_code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
]


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

    
