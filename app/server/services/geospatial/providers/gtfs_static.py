from __future__ import annotations

import csv
import io
import zipfile
from typing import Any

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)


class GTFSStaticProvider(GeospatialProvider):
    provider_id = "gtfs_static"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        feed_bytes = request.params.get("feed_bytes")
        feed_url = str(request.params.get("feed_url") or "").strip()
        if isinstance(feed_bytes, bytes):
            payload = self._parse_feed(feed_bytes)
        elif feed_url:
            payload = {
                "renderingMode": "metadata-only",
                "feedUrl": feed_url,
                "status": "download-required",
                "message": "GTFS static feed download is handled by the ingestion pipeline.",
            }
        else:
            payload = {
                "renderingMode": "metadata-only",
                "status": "feed-required",
                "message": "Provide a GTFS static feed URL or ingested feed bytes before rendering stops and routes.",
            }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=["GTFS Static feed publisher"],
        )

    def _parse_feed(self, feed_bytes: bytes) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(io.BytesIO(feed_bytes)) as archive:
                stops = self._read_csv(archive, "stops.txt")
                routes = self._read_csv(archive, "routes.txt")
                shapes = self._read_csv(archive, "shapes.txt")
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, csv.Error) as exc:
            raise ProviderUnavailableError(f"Invalid GTFS static feed: {exc}") from exc

        return {
            "renderingMode": "clustered-points",
            "stops": [self._stop_feature(row) for row in stops if self._has_stop_geometry(row)],
            "routes": [self._route_feature(row) for row in routes],
            "shapePointCount": sum(1 for row in shapes if row.get("shape_pt_lat") and row.get("shape_pt_lon")),
            "summary": {
                "stopCount": len(stops),
                "routeCount": len(routes),
                "shapePointCount": len(shapes),
            },
        }

    def _read_csv(self, archive: zipfile.ZipFile, filename: str) -> list[dict[str, str]]:
        try:
            raw = archive.read(filename)
        except KeyError:
            return []
        text = raw.decode("utf-8-sig")
        return [dict(row) for row in csv.DictReader(io.StringIO(text))]

    def _has_stop_geometry(self, row: dict[str, str]) -> bool:
        return bool(row.get("stop_lat") and row.get("stop_lon"))

    def _stop_feature(self, row: dict[str, str]) -> dict[str, Any]:
        return {
            "id": row.get("stop_id") or row.get("stop_code") or row.get("stop_name"),
            "name": row.get("stop_name"),
            "latitude": self._float_or_none(row.get("stop_lat")),
            "longitude": self._float_or_none(row.get("stop_lon")),
            "metadata": {
                "code": row.get("stop_code"),
                "zone": row.get("zone_id"),
                "url": row.get("stop_url"),
            },
        }

    def _route_feature(self, row: dict[str, str]) -> dict[str, Any]:
        return {
            "id": row.get("route_id"),
            "shortName": row.get("route_short_name"),
            "longName": row.get("route_long_name"),
            "type": row.get("route_type"),
            "color": row.get("route_color"),
            "textColor": row.get("route_text_color"),
        }

    def _float_or_none(self, value: str | None) -> float | None:
        if value is None or not str(value).strip():
            return None
        try:
            return float(value)
        except ValueError:
            return None
