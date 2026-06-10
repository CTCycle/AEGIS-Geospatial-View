from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider


###############################################################################
def test_gtfs_realtime_vehicle_positions_require_fresh_feed() -> None:
    response = asyncio.run(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": 946684800},
                        "entities": [
                            {
                                "vehicle": {
                                    "id": "vehicle-1",
                                    "position": {"latitude": 41.9, "longitude": 12.5},
                                }
                            }
                        ],
                    },
                    "feed_freshness_seconds": 60,
                },
            )
        )
    )

    assert response.payload["summary"]["vehicleCount"] == 1
    assert response.payload["summary"]["renderedVehicleCount"] == 0
    assert response.payload["vehicles"] == []
    assert response.payload["vehicleRenderingAllowed"] is False
