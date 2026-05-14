from __future__ import annotations

import csv
import io
import zipfile
from typing import Any

from server.services.geospatial.cache import CacheLookupStatus, GeospatialCache
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    BytesFetcher,
    call_bytes_fetcher,
    fetch_bytes_url,
)


class GTFSStaticProvider(GeospatialProvider):
    provider_id = "gtfs_static"

    def __init__(
        self,
        *,
        fetcher: BytesFetcher | None = None,
        cache: GeospatialCache | None = None,
    ) -> None:
        self.fetcher = fetcher or fetch_bytes_url
        self.cache = cache or GeospatialCache()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        feed_bytes = request.params.get("feed_bytes")
        feed_url = str(request.params.get("feed_url") or "").strip()
        if isinstance(feed_bytes, bytes):
            payload = self._parse_feed(feed_bytes)
        elif feed_url:
            payload = await self._fetch_and_parse_feed(feed_url)
        else:
            payload = {
                "renderingMode": "metadata-only",
                "status": "configuration-needed",
                "message": "Configure a GTFS static feed URL or provide ingested feed bytes before rendering stops and routes.",
            }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=["GTFS Static feed publisher"],
        )

    async def fetch_features(self, request: ProviderRequest) -> ProviderResponse:
        return await self.fetch(request)

    async def _fetch_and_parse_feed(self, feed_url: str) -> dict[str, Any]:
        cache_key = f"{self.provider_id}:{feed_url}"
        try:
            feed_bytes = await call_bytes_fetcher(self.fetcher, feed_url, None)
            payload = self._parse_feed(feed_bytes)
            payload["feedUrl"] = feed_url
            self.cache.set(
                cache_key,
                payload,
                ttl_seconds=86400,
                stale_while_revalidate_seconds=604800,
            )
            return payload
        except ProviderError:
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.STALE and isinstance(cached.value, dict):
                stale_payload = dict(cached.value)
                stale_payload["stale"] = True
                stale_payload.setdefault("warnings", []).append(
                    "GTFS static feed fetch failed; serving stale parsed feed."
                )
                return stale_payload
            raise

    def _parse_feed(self, feed_bytes: bytes) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(io.BytesIO(feed_bytes)) as archive:
                stops = self._read_csv(archive, "stops.txt")
                routes = self._read_csv(archive, "routes.txt")
                agency = self._read_csv(archive, "agency.txt")
                calendar = self._read_csv(archive, "calendar.txt")
                shapes = self._read_csv(archive, "shapes.txt")
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, csv.Error) as exc:
            raise ProviderUnavailableError(f"Invalid GTFS static feed: {exc}") from exc

        shape_lines = self._shape_lines(shapes)
        return {
            "renderingMode": "clustered-points",
            "stops": [
                self._stop_feature(row) for row in stops if self._has_stop_geometry(row)
            ],
            "routes": [self._route_feature(row) for row in routes],
            "shapes": shape_lines,
            "agency": [self._agency_record(row) for row in agency],
            "calendar": [self._calendar_record(row) for row in calendar],
            "shapePointCount": sum(
                1
                for row in shapes
                if row.get("shape_pt_lat") and row.get("shape_pt_lon")
            ),
            "summary": {
                "stopCount": len(stops),
                "routeCount": len(routes),
                "agencyCount": len(agency),
                "calendarCount": len(calendar),
                "shapeCount": len(shape_lines),
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

    def _agency_record(self, row: dict[str, str]) -> dict[str, Any]:
        return {
            "id": row.get("agency_id") or row.get("agency_name"),
            "name": row.get("agency_name"),
            "url": row.get("agency_url"),
            "timezone": row.get("agency_timezone"),
            "language": row.get("agency_lang"),
            "phone": row.get("agency_phone"),
        }

    def _calendar_record(self, row: dict[str, str]) -> dict[str, Any]:
        return {
            "serviceId": row.get("service_id"),
            "days": {
                day: row.get(day) == "1"
                for day in (
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                )
            },
            "startDate": row.get("start_date"),
            "endDate": row.get("end_date"),
        }

    def _shape_lines(self, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            shape_id = row.get("shape_id")
            if not shape_id:
                continue
            grouped.setdefault(shape_id, []).append(row)
        features = []
        for shape_id, points in grouped.items():
            ordered = sorted(points, key=lambda row: self._sequence(row))
            coordinates = [
                [lon, lat]
                for row in ordered
                if (lat := self._float_or_none(row.get("shape_pt_lat"))) is not None
                and (lon := self._float_or_none(row.get("shape_pt_lon"))) is not None
            ]
            if len(coordinates) < 2:
                continue
            features.append(
                {
                    "id": shape_id,
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coordinates,
                    },
                    "properties": {"shape_id": shape_id},
                }
            )
        return features

    def _sequence(self, row: dict[str, str]) -> int:
        value = row.get("shape_pt_sequence")
        try:
            return int(value or "0")
        except ValueError:
            return 0

    def _float_or_none(self, value: str | None) -> float | None:
        if value is None or not str(value).strip():
            return None
        try:
            return float(value)
        except ValueError:
            return None
