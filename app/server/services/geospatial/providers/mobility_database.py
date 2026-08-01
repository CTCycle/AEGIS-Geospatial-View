from __future__ import annotations

from server.common.typing import json_object

import csv
import io
import os
from pathlib import Path
from typing import Any

from server.common.paths import resolve_runtime_data_root
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    TextFetcher,
    call_text_fetcher,
    fetch_text_url,
)

MOBILITY_DATABASE_CSV_URL = "https://files.mobilitydatabase.org/feeds_v2.csv"

###############################################################################
class MobilityDatabaseProvider(GeospatialProvider):
    """Search the locally cached Mobility Database feed catalog."""

    provider_id = "mobility_database"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        catalog_path: str | Path | None = None,
        fetcher: TextFetcher | None = None,
        catalog_url: str = MOBILITY_DATABASE_CSV_URL,
    ) -> None:
        self.catalog_path = Path(
            catalog_path
            or os.getenv(
                "AEGIS_MOBILITY_DATABASE_CATALOG_PATH",
                str(resolve_runtime_data_root() / "geospatial" / "mobility_database_feeds_v2.csv"),
            )
        ).expanduser()
        self.fetcher = fetcher or fetch_text_url
        self.catalog_url = catalog_url

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        rows = await self._load_rows(refresh=_is_true(request.params.get("refresh")))
        query = str(request.params.get("query") or "").strip().casefold()
        limit = _bounded_limit(request.params.get("limit"))
        feeds = [
            normalized
            for row in rows
            if (normalized := self._normalize_row(row)) is not None
            and self._matches(normalized, query=query, bbox=request.bbox)
        ]
        feeds.sort(key=lambda item: (str(item.get("name") or item.get("provider") or "").casefold(), str(item.get("id") or "")))
        feeds = feeds[:limit]
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "renderingMode": "metadata-only",
                "type": "search-index",
                "source": "Mobility Database Catalog",
                "catalogUrl": self.catalog_url,
                "feeds": feeds,
                "feedCount": len(feeds),
                "catalogRecordCount": len(rows),
            },
            attribution=["Mobility Database Catalog (CC0 metadata)"],
        )

    # -------------------------------------------------------------------------
    async def _load_rows(self, *, refresh: bool) -> list[dict[str, str]]:
        if refresh or not self.catalog_path.is_file():
            try:
                text = await call_text_fetcher(self.fetcher, self.catalog_url, None)
                self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
                self.catalog_path.write_text(text, encoding="utf-8")
            except Exception as exc:
                if not self.catalog_path.is_file():
                    raise ProviderUnavailableError(
                        "Mobility Database catalog is unavailable and could not be downloaded."
                    ) from exc
        try:
            return list(csv.DictReader(io.StringIO(self.catalog_path.read_text(encoding="utf-8-sig"))))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ProviderUnavailableError("Mobility Database catalog is malformed.") from exc

    # -------------------------------------------------------------------------
    def _normalize_row(self, row: dict[str, str]) -> dict[str, Any] | None:
        source_id = _first(row, "mdb_source_id", "id", "source_id")
        provider = _first(row, "provider", "provider_name")
        if not source_id and not provider:
            return None
        bbox = {
            "minimumLatitude": _float(_first(row, "location.bounding_box.minimum_latitude", "minimum_latitude")),
            "maximumLatitude": _float(_first(row, "location.bounding_box.maximum_latitude", "maximum_latitude")),
            "minimumLongitude": _float(_first(row, "location.bounding_box.minimum_longitude", "minimum_longitude")),
            "maximumLongitude": _float(_first(row, "location.bounding_box.maximum_longitude", "maximum_longitude")),
        }
        authentication_type = _first(row, "urls.authentication_type", "authentication_type") or "0"
        return {
            "id": source_id,
            "name": _first(row, "name", "feed_name") or provider,
            "provider": provider,
            "countryCode": _first(row, "location.country_code", "country_code"),
            "subdivisionName": _first(row, "location.subdivision_name", "subdivision_name"),
            "municipality": _first(row, "location.municipality", "municipality"),
            "dataType": _first(row, "data_type"),
            "status": _first(row, "status") or "active",
            "isOfficial": _bool(_first(row, "is_official")),
            "staticFeedUrl": _first(row, "urls.latest", "latest", "latest.url", "urls.direct_download"),
            "license": _first(row, "urls.license", "license", "license_url"),
            "authentication": {
                "type": authentication_type,
                "required": authentication_type not in {"", "0", "none", "None"},
                "infoUrl": _first(row, "urls.authentication_info_url", "authentication_info_url"),
                "apiKeyParameterName": _first(row, "urls.api_key_parameter_name", "api_key_parameter_name"),
            },
            "realtimeUrl": _first(row, "urls.direct_download_url", "direct_download_url"),
            "bbox": bbox,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _matches(item: dict[str, Any], *, query: str, bbox: tuple[float, float, float, float] | None) -> bool:
        if query:
            haystack = " ".join(
                str(item.get(key) or "")
                for key in ("id", "name", "provider", "countryCode", "subdivisionName", "municipality")
            ).casefold()
            if query not in haystack:
                return False
        if bbox:
            item_bbox = json_object(item.get("bbox"))
            west, south, east, north = bbox
            min_lon = item_bbox.get("minimumLongitude")
            max_lon = item_bbox.get("maximumLongitude")
            min_lat = item_bbox.get("minimumLatitude")
            max_lat = item_bbox.get("maximumLatitude")
            if all(value is not None for value in (min_lon, max_lon, min_lat, max_lat)) and (
                float(str(max_lon)) < west or float(str(min_lon)) > east or float(str(max_lat)) < south or float(str(min_lat)) > north
            ):
                return False
        return True

###############################################################################
def _first(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None

###############################################################################
def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

###############################################################################
def _bool(value: str | None) -> bool | None:
    if value is None or not value.strip():
        return None
    return value.strip().casefold() in {"true", "1", "yes"}

###############################################################################
def _bounded_limit(value: object) -> int:
    try:
        return max(1, min(200, int(str(value or 50))))
    except (TypeError, ValueError):
        return 50

###############################################################################
def _is_true(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "refresh"}
