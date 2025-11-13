from __future__ import annotations

from typing import Any

import pandas as pd

from AEGIS.src.packages.utils.repository.database import database


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

GIBS_LAYER_COLUMNS = [
    "layer_id",
    "title",
    "abstract",
    "projections",
    "source_urls",
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

    # -----------------------------------------------------------------------------
    def upsert_gibs_layers(self, layers: list[dict[str, Any]]) -> None:
        if not layers:
            return
        frame = pd.DataFrame.from_records(layers)
        frame = frame.reindex(columns=GIBS_LAYER_COLUMNS)
        frame = frame.where(pd.notnull(frame), None)
        database.upsert_into_database(frame, "GIBS_LAYERS")
