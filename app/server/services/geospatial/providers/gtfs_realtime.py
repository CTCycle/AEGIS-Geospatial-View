from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderUnavailableError,
)


class GTFSRealtimeProvider(GeospatialProvider):
    provider_id = "gtfs_realtime"

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        decoded_feed = request.params.get("decoded_feed")
        feed_url = str(request.params.get("feed_url") or "").strip()
        feed_bytes = request.params.get("feed_bytes")
        if isinstance(decoded_feed, dict):
            payload = self._normalize_decoded_feed(decoded_feed)
        elif isinstance(feed_bytes, bytes):
            payload = self._parse_protobuf(feed_bytes)
        elif feed_url:
            payload = {
                "renderingMode": "metadata-only",
                "feedUrl": feed_url,
                "status": "fetch-required",
                "message": "GTFS Realtime feed fetching is performed by configured feed adapters.",
            }
        else:
            payload = {
                "renderingMode": "metadata-only",
                "status": "feed-required",
                "message": "Provide a GTFS Realtime feed URL or decoded feed payload before rendering vehicles and alerts.",
            }
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=payload,
            attribution=["GTFS Realtime feed publisher"],
        )

    def _parse_protobuf(self, feed_bytes: bytes) -> dict[str, Any]:
        try:
            from google.transit import gtfs_realtime_pb2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderUnavailableError(
                "GTFS Realtime protobuf parser is unavailable; install gtfs-realtime-bindings."
            ) from exc
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
            }
        )

    def _normalize_decoded_feed(self, feed: dict[str, Any]) -> dict[str, Any]:
        entities = [entity for entity in feed.get("entities") or [] if isinstance(entity, dict)]
        vehicles = [entity["vehicle"] for entity in entities if isinstance(entity.get("vehicle"), dict)]
        alerts = [entity["alert"] for entity in entities if isinstance(entity.get("alert"), dict)]
        trip_updates = [
            entity["tripUpdate"]
            for entity in entities
            if isinstance(entity.get("tripUpdate"), dict)
        ]
        return {
            "renderingMode": "clustered-points",
            "vehicles": [self._vehicle_feature(vehicle) for vehicle in vehicles],
            "alerts": alerts,
            "tripUpdates": trip_updates,
            "summary": {
                "vehicleCount": len(vehicles),
                "alertCount": len(alerts),
                "tripUpdateCount": len(trip_updates),
            },
            "feedTimestamp": self._feed_timestamp(feed.get("header")),
        }

    def _vehicle_feature(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        position = vehicle.get("position") if isinstance(vehicle.get("position"), dict) else {}
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
