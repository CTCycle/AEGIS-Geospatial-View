from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider


def test_gtfs_realtime_provider_normalizes_trip_updates_alerts_and_vehicles() -> None:
    now = int(datetime.now(UTC).timestamp())

    response = asyncio.run(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": now},
                        "entities": [
                            {"tripUpdate": {"tripId": "trip-1", "routeId": "r1"}},
                            {"alert": {"effect": "DELAY", "header": "Delay"}},
                            {
                                "vehicle": {
                                    "id": "vehicle-1",
                                    "routeId": "r1",
                                    "position": {"latitude": 41.9, "longitude": 12.5},
                                }
                            },
                        ],
                    }
                },
            )
        )
    )

    assert response.payload["summary"]["tripUpdateCount"] == 1
    assert response.payload["summary"]["alertCount"] == 1
    assert response.payload["summary"]["vehicleCount"] == 1
    assert response.payload["vehicleRenderingAllowed"] is True


def test_gtfs_realtime_provider_fetches_configured_protobuf_feed_url() -> None:
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(datetime.now(UTC).timestamp())
    entity = feed.entity.add()
    entity.id = "alert-1"
    entity.alert.effect = gtfs_realtime_pb2.Alert.DETOUR
    feed_bytes = feed.SerializeToString()
    calls: list[str] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None) -> bytes:
        calls.append(url)
        return feed_bytes

    response = asyncio.run(
        GTFSRealtimeProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={"feed_url": "https://agency.example/gtfs-rt.pb"},
            )
        )
    )

    assert calls == ["https://agency.example/gtfs-rt.pb"]
    assert response.payload["feedUrl"] == "https://agency.example/gtfs-rt.pb"
    assert response.payload["summary"]["alertCount"] == 1
