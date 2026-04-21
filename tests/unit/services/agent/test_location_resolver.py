from __future__ import annotations

import asyncio

from AEGIS.server.services.agent.location_resolver import LocationResolver
from AEGIS.server.domain.extraction.models import LocationSignal


def test_location_resolver_uses_coordinates_without_geocoder() -> None:
    resolver = LocationResolver()

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                LocationSignal(
                    signal_type="coordinates",
                    raw_value="41.9, 12.5",
                    latitude=41.9,
                    longitude=12.5,
                    confidence=0.95,
                )
            ],
            {},
        )
        assert result.latitude == 41.9
        assert result.longitude == 12.5

    asyncio.run(_run())
