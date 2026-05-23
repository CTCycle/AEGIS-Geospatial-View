from __future__ import annotations

from datetime import UTC, datetime
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

gtfs_realtime_pb2: Any | None
try:
    from google.transit import gtfs_realtime_pb2  # type: ignore[import-not-found]
except ImportError:
    gtfs_realtime_pb2 = None


class GTFSRealtimeProvider(GeospatialProvider):
    provider_id = "gtfs_realtime"

    def __init__(
        self,
        *,
        fetcher: BytesFetcher | None = None,
        cache: GeospatialCache | None = None,
    ) -> None:
        self.fetcher = fetcher or fetch_bytes_url
        self.cache = cache or GeospatialCache()

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        decoded_feed = request.params.get("decoded_feed")
        feed_url = str(request.params.get("feed_url") or "").strip()
        feed_bytes = request.params.get("feed_bytes")
        if isinstance(decoded_feed, dict):
            payload = self._normalize_decoded_feed(decoded_feed, request=request)
        elif isinstance(feed_bytes, bytes):
            payload = self._parse_protobuf(feed_bytes, request=request)
        elif feed_url:
            payload = await self._fetch_and_parse_feed(feed_url, request=request)
        else:
            payload = {
                "renderingMode": "metadata-only",
                "status": "configuration-needed",
                "message": "Configure a GTFS Realtime feed URL or decoded feed payload before rendering vehicles and alerts.",
            }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=["GTFS Realtime feed publisher"],
        )

    async def fetch_features(self, request: ProviderRequest) -> ProviderResponse:
        return await self.fetch(request)

    async def _fetch_and_parse_feed(
        self, feed_url: str, *, request: ProviderRequest
    ) -> dict[str, Any]:
        cache_key = f"{self.provider_id}:{feed_url}"
        try:
            feed_bytes = await call_bytes_fetcher(self.fetcher, feed_url, None)
            payload = self._parse_protobuf(feed_bytes, request=request)
            payload["feedUrl"] = feed_url
            self.cache.set(
                cache_key,
                payload,
                ttl_seconds=60,
                stale_while_revalidate_seconds=300,
            )
            return payload
        except ProviderError:
            cached = self.cache.get(cache_key)
            if cached.status == CacheLookupStatus.STALE and isinstance(
                cached.value, dict
            ):
                stale_payload = dict(cached.value)
                stale_payload["stale"] = True
                stale_payload.setdefault("warnings", []).append(
                    "GTFS Realtime feed fetch failed; serving stale parsed feed."
                )
                return stale_payload
            raise

    def _parse_protobuf(
        self, feed_bytes: bytes, *, request: ProviderRequest | None = None
    ) -> dict[str, Any]:
        if gtfs_realtime_pb2 is None:
            raise ProviderUnavailableError(
                "GTFS Realtime protobuf parser is unavailable; install gtfs-realtime-bindings."
            )
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(feed_bytes)
        entities: list[dict[str, Any]] = []
        for entity in feed.entity:
            entities.append(
                {
                    "id": entity.id,
                    "vehicle": self._vehicle_from_entity(entity),
                    "alert": self._alert_from_entity(entity),
                    "tripUpdate": {"tripId": entity.trip_update.trip.trip_id}
                    if entity.HasField("trip_update")
                    else None,
                }
            )
        return self._normalize_decoded_feed(
            {
                "header": {
                    "timestamp": int(feed.header.timestamp),
                    "incrementality": int(feed.header.incrementality),
                },
                "entities": entities,
            },
            request=request,
        )

    def _normalize_decoded_feed(
        self, feed: dict[str, Any], *, request: ProviderRequest | None = None
    ) -> dict[str, Any]:
        entities = [
            entity for entity in feed.get("entities") or [] if isinstance(entity, dict)
        ]
        vehicles = [
            entity["vehicle"]
            for entity in entities
            if isinstance(entity.get("vehicle"), dict)
        ]
        alerts = [
            self._alert_feature(entity["alert"])
            for entity in entities
            if isinstance(entity.get("alert"), dict)
        ]
        trip_updates = [
            self._trip_update_feature(entity["tripUpdate"])
            for entity in entities
            if isinstance(entity.get("tripUpdate"), dict)
        ]
        feed_timestamp = self._feed_timestamp(feed.get("header"))
        vehicle_rendering_allowed = self._vehicle_rendering_allowed(
            feed_timestamp,
            request=request,
        )
        return {
            "renderingMode": "clustered-points",
            "vehicles": [self._vehicle_feature(vehicle) for vehicle in vehicles]
            if vehicle_rendering_allowed
            else [],
            "alerts": alerts,
            "tripUpdates": trip_updates,
            "summary": {
                "vehicleCount": len(vehicles),
                "renderedVehicleCount": len(vehicles)
                if vehicle_rendering_allowed
                else 0,
                "alertCount": len(alerts),
                "tripUpdateCount": len(trip_updates),
            },
            "feedTimestamp": feed_timestamp,
            "vehicleRenderingAllowed": vehicle_rendering_allowed,
        }

    def _vehicle_feature(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        position = (
            vehicle.get("position") if isinstance(vehicle.get("position"), dict) else {}
        )
        return {
            "id": vehicle.get("id") or vehicle.get("vehicleId") or vehicle.get("label"),
            "tripId": vehicle.get("tripId"),
            "routeId": vehicle.get("routeId"),
            "latitude": position.get("latitude"),
            "longitude": position.get("longitude"),
            "bearing": position.get("bearing"),
            "speed": position.get("speed"),
            "timestamp": vehicle.get("timestamp"),
        }

    def _feed_timestamp(self, header: Any) -> str | None:
        if not isinstance(header, dict):
            return None
        value = header.get("timestamp")
        if not isinstance(value, (int, float)) or value <= 0:
            return None
        return datetime.fromtimestamp(value, tz=UTC).isoformat()

    def _vehicle_rendering_allowed(
        self, feed_timestamp: str | None, *, request: ProviderRequest | None
    ) -> bool:
        params = request.params if request is not None else {}
        if params.get("allow_vehicle_rendering") is False:
            return False
        if not feed_timestamp:
            return False
        freshness_seconds = params.get("feed_freshness_seconds", 120)
        try:
            max_age = float(freshness_seconds)
            timestamp = datetime.fromisoformat(feed_timestamp)
        except (TypeError, ValueError):
            return False
        return (datetime.now(UTC) - timestamp).total_seconds() <= max_age

    def _trip_update_feature(self, trip_update: dict[str, Any]) -> dict[str, Any]:
        return {
            "tripId": trip_update.get("tripId") or trip_update.get("trip_id"),
            "routeId": trip_update.get("routeId") or trip_update.get("route_id"),
            "delay": trip_update.get("delay"),
            "stopTimeUpdates": trip_update.get("stopTimeUpdates")
            or trip_update.get("stop_time_updates")
            or [],
        }

    def _alert_feature(self, alert: dict[str, Any]) -> dict[str, Any]:
        return {
            "cause": alert.get("cause"),
            "effect": alert.get("effect"),
            "header": alert.get("header") or alert.get("headerText"),
            "description": alert.get("description") or alert.get("descriptionText"),
            "activePeriodCount": alert.get("activePeriodCount")
            or len(alert.get("activePeriods") or []),
        }

    def _vehicle_from_entity(self, entity: Any) -> dict[str, Any] | None:
        if not entity.HasField("vehicle"):
            return None
        vehicle = entity.vehicle
        return {
            "id": vehicle.vehicle.id,
            "label": vehicle.vehicle.label,
            "tripId": vehicle.trip.trip_id,
            "routeId": vehicle.trip.route_id,
            "timestamp": int(vehicle.timestamp),
            "position": {
                "latitude": float(vehicle.position.latitude),
                "longitude": float(vehicle.position.longitude),
                "bearing": float(vehicle.position.bearing),
                "speed": float(vehicle.position.speed),
            },
        }

    def _alert_from_entity(self, entity: Any) -> dict[str, Any] | None:
        if not entity.HasField("alert"):
            return None
        alert = entity.alert
        return {
            "cause": int(alert.cause),
            "effect": int(alert.effect),
            "activePeriodCount": len(alert.active_period),
        }
