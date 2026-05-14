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
