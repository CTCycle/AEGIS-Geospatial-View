from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from AEGIS.server.utils.constants import (
    BROWSER_ROUTER_PREFIX,
    BROWSER_TABLE_ROUTE,
    BROWSER_TABLE_STATS_ROUTE,
    BROWSER_TABLES_ROUTE,
)
from AEGIS.server.utils.logger import logger
from AEGIS.server.repositories.serialization import DataSerializer

router = APIRouter(prefix=BROWSER_ROUTER_PREFIX, tags=["browser"])
serializer = DataSerializer()

# Table name mapping: internal name -> display name
TABLE_MAPPING: dict[str, str] = {
    "GIBS_LAYERS": "GIBS Satellite Layers",
    "SEARCH_SESSIONS": "Search History",
}


# -----------------------------------------------------------------------------
@router.get(BROWSER_TABLES_ROUTE)
def list_tables() -> JSONResponse:
    """List all available tables with verbose display names."""
    tables = [
        {"name": name, "displayName": display_name}
        for name, display_name in TABLE_MAPPING.items()
    ]
    return JSONResponse(content=jsonable_encoder({"tables": tables}))


# -----------------------------------------------------------------------------
@router.get(BROWSER_TABLE_ROUTE)
def get_table_data(table_name: str) -> JSONResponse:
    """Fetch all data from a specific table."""
    if table_name not in TABLE_MAPPING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found.",
        )
    try:
        payload = serializer.load_table_records(table_name)
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "tableName": table_name,
                    "displayName": TABLE_MAPPING[table_name],
                    "columns": payload["columns"],
                    "rows": payload["rows"],
                    "rowCount": payload["row_count"],
                    "columnCount": payload["column_count"],
                }
            )
        )
    except Exception as e:
        logger.error("Error loading table %s: %s", table_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load table: {e}",
        )


# -----------------------------------------------------------------------------
@router.get(BROWSER_TABLE_STATS_ROUTE)
def get_table_stats(table_name: str) -> JSONResponse:
    """Get statistics for a specific table."""
    if table_name not in TABLE_MAPPING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found.",
        )
    try:
        stats = serializer.get_table_stats(table_name)
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "tableName": table_name,
                    "displayName": TABLE_MAPPING[table_name],
                    "rowCount": stats["row_count"],
                    "columnCount": stats["column_count"],
                }
            )
        )
    except Exception as e:
        logger.error("Error getting stats for table %s: %s", table_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get table stats: {e}",
        )
