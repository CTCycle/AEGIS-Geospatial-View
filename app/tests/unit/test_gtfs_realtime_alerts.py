from __future__ import annotations

import asyncio

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider


###############################################################################
def test_gtfs_realtime_alerts_render_popup_fields() -> None:
    response = asyncio.run(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": 946684800},
                        "entities": [
                            {
                                "alert": {
                                    "cause": "CONSTRUCTION",
                                    "effect": "DETOUR",
                                    "header": "Route detour",
                                    "description": "Use alternate stop.",
                                    "activePeriods": [{"start": 1, "end": 2}],
                                }
                            }
                        ],
                    }
                },
            )
        )
    )

    alert = response.payload["alerts"][0]
    assert alert["cause"] == "CONSTRUCTION"
    assert alert["effect"] == "DETOUR"
    assert alert["header"] == "Route detour"
    assert alert["description"] == "Use alternate stop."
    assert alert["activePeriodCount"] == 1
