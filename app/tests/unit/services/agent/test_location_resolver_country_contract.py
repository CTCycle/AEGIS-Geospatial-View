from __future__ import annotations

import asyncio

import pytest

from server.contracts.extraction import LocationSignal
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.location_resolver import LocationResolver


class _CountryGeocoder:
    def __init__(self, target: str, code: str, *, subordinate: bool = False) -> None:
        self.target = target
        self.code = code
        self.subordinate = subordinate

    async def extract_coordinates(self, **_: object) -> dict[str, object]:
        if self.subordinate:
            display = f"{self.target} Region, {self.target}"
            name = f"{self.target} Region"
        else:
            display = self.target
            name = self.target
        return {
            "display_name": display,
            "name": name,
            "lat": 10.0,
            "lon": 20.0,
            "selected_result_type": "administrative",
            "address": {
                "country": self.target,
                "country_code": self.code,
            },
        }


@pytest.mark.parametrize(
    ("country", "code"),
    [
        ("France", "fr"),
        ("Germany", "de"),
        ("Italy", "it"),
        ("Iceland", "is"),
        ("Japan", "jp"),
        ("Switzerland", "ch"),
    ],
)
def test_country_administrative_boundary_requires_matching_country_identity(
    country: str, code: str
) -> None:
    resolver = LocationResolver(nominatim_service=_CountryGeocoder(country, code))

    result = asyncio.run(
        resolver.resolve_location_signals(
            [LocationSignal(signal_type="country", raw_value=country)], {}
        )
    )

    assert isinstance(result, ResolvedLocation)
    assert result.location_type == "country"


def test_country_rejects_subordinate_administrative_region() -> None:
    resolver = LocationResolver(
        nominatim_service=_CountryGeocoder("France", "fr", subordinate=True)
    )

    result = asyncio.run(
        resolver.resolve_location_signals(
            [LocationSignal(signal_type="country", raw_value="France")], {}
        )
    )

    assert not isinstance(result, ResolvedLocation)
    assert result.missing_fields == ["location"]


def test_country_rejects_mismatched_country_code() -> None:
    resolver = LocationResolver(nominatim_service=_CountryGeocoder("France", "de"))

    result = asyncio.run(
        resolver.resolve_location_signals(
            [LocationSignal(signal_type="country", raw_value="France")], {}
        )
    )

    assert not isinstance(result, ResolvedLocation)
    assert result.missing_fields == ["location"]
