from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from AEGIS.server.database.database import database
from AEGIS.server.utils.logger import logger

router = APIRouter(prefix="/browser", tags=["browser"])

# Table name mapping: internal name -> display name
TABLE_MAPPING: dict[str, str] = {
    "GIBS_LAYERS": "GIBS Satellite Layers",
    "SEARCH_SESSIONS": "Search History",
}


# -----------------------------------------------------------------------------
@router.get("/tables")
def list_tables() -> JSONResponse:
    """List all available tables with verbose display names."""
    tables = [
        {"name": name, "displayName": display_name}
        for name, display_name in TABLE_MAPPING.items()
    ]
    return JSONResponse(content=jsonable_encoder({"tables": tables}))


# -----------------------------------------------------------------------------
@router.get("/tables/{table_name}")
def get_table_data(table_name: str) -> JSONResponse:
    """Fetch all data from a specific table."""
    if table_name not in TABLE_MAPPING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found.",
        )
    try:
        df = database.load_from_database(table_name)
        columns = df.columns.tolist()
        rows = df.to_dict(orient="records")
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "tableName": table_name,
                    "displayName": TABLE_MAPPING[table_name],
                    "columns": columns,
                    "rows": rows,
                    "rowCount": len(rows),
                    "columnCount": len(columns),
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
@router.get("/tables/{table_name}/stats")
def get_table_stats(table_name: str) -> JSONResponse:
    """Get statistics for a specific table."""
    if table_name not in TABLE_MAPPING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found.",
        )
    try:
        df = database.load_from_database(table_name)
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "tableName": table_name,
                    "displayName": TABLE_MAPPING[table_name],
                    "rowCount": len(df),
                    "columnCount": len(df.columns),
                }
            )
        )
    except Exception as e:
        logger.error("Error getting stats for table %s: %s", table_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get table stats: {e}",
        )
