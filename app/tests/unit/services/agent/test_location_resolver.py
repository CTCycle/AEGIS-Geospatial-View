from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.agent.location_resolver import LocationResolver
from server.contracts.extraction import LocationSignal


###############################################################################
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

    run_async_in_thread(_run())


###############################################################################
def test_location_resolver_prefers_specific_city_signal_over_country() -> None:

    ###############################################################################
    class _FakeNominatim:
        # -------------------------------------------------------------------------
        async def extract_coordinates(
            self,
            *,
            address: str,
            city: str | None,
            country_name: str | None,
            country_code: str | None,
            expected_location_type: str | None = None,
        ) -> dict[str, object] | None:
            _ = (city, country_name, country_code, expected_location_type)
            lookup = {
                "Rome": {
                    "display_name": "Rome, Lazio, Italy",
                    "lat": 41.9028,
                    "lon": 12.4964,
                    "confidence": 0.62,
                    "provider": "nominatim",
                    "source_url": "https://nominatim.openstreetmap.org/search",
                    "fetched_at": "2026-09-01T10:00:00+00:00",
                },
                "Italy": {
                    "display_name": "Italy",
                    "lat": 41.8719,
                    "lon": 12.5674,
                    "confidence": 0.61,
                    "provider": "nominatim",
                    "source_url": "https://nominatim.openstreetmap.org/search",
                    "fetched_at": "2026-09-01T10:00:00+00:00",
                },
            }
            return lookup.get(address)

    resolver = LocationResolver(nominatim_service=_FakeNominatim())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                LocationSignal(
                    signal_type="country",
                    raw_value="Italy",
                    normalized_value="Italy",
                    confidence=0.93,
                ),
                LocationSignal(
                    signal_type="city",
                    raw_value="Rome",
                    normalized_value="Rome",
                    confidence=0.93,
                ),
            ],
            {},
        )
        assert result.label == "Rome, Lazio, Italy"
        assert result.latitude == 41.9028
        assert result.longitude == 12.4964
        assert result.provenance is not None
        assert result.provenance.provider == "nominatim"
        assert result.provenance.source_url.endswith("/search")

    run_async_in_thread(_run())
