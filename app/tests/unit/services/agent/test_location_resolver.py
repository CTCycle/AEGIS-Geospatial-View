from __future__ import annotations

import pytest
import unicodedata

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

    calls: list[dict[str, object]] = []

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
            calls.append(
                {
                    "address": address,
                    "city": city,
                    "country_name": country_name,
                    "country_code": country_code,
                    "expected_location_type": expected_location_type,
                }
            )
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
                    confidence=0.99,
                ),
                LocationSignal(
                    signal_type="city",
                    raw_value="Rome",
                    normalized_value="Rome",
                    confidence=0.20,
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
        assert calls == [
            {
                "address": "Rome",
                "city": None,
                "country_name": "Italy",
                "country_code": None,
                "expected_location_type": "city",
            }
        ]

    run_async_in_thread(_run())


###############################################################################
def test_location_resolver_accepts_poi_when_parent_signal_is_canonicalized() -> None:
    class _CanonicalizedParent:
        async def extract_coordinates(self, **kwargs):  # noqa: ANN003, ANN201
            assert kwargs["city"] == "Rome, Roma Capitale, Lazio, Italy"
            return {
                "display_name": (
                    "Colosseum, Celio, Municipio Roma I, Rome, "
                    "Roma Capitale, Lazio, 00184, Italy"
                ),
                "lat": 41.8909421,
                "lon": 12.491903,
                "selected_result_type": "pedestrian",
                "selected_result_class": "highway",
                "selected_address_type": "road",
                "address": {
                    "pedestrian": "Colosseum",
                    "city": "Rome",
                    "state": "Lazio",
                    "country": "Italy",
                    "country_code": "it",
                },
                "namedetails": {"name:en": "Colosseum"},
            }

    resolver = LocationResolver(nominatim_service=_CanonicalizedParent())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                LocationSignal(
                    signal_type="poi",
                    raw_value="Colosseum",
                    normalized_value="Colosseum",
                ),
                LocationSignal(
                    signal_type="city",
                    raw_value="Rome, Italy",
                    normalized_value="Rome, Roma Capitale, Lazio, Italy",
                    latitude=41.8933203,
                    longitude=12.4829321,
                ),
            ],
            {},
        )
        assert result.label.startswith("Colosseum")
        assert result.latitude == 41.8909421
        assert result.longitude == 12.491903

    run_async_in_thread(_run())


###############################################################################
@pytest.mark.parametrize(
    ("signal_type", "raw_value", "display_name"),
    [
        ("city", "München", "München, Bayern, Deutschland"),
        ("city", "Sao Paulo", "São Paulo, Brasil"),
        ("address", "Central Station", "Central Station, Metro City, Countryland"),
    ],
)
def test_location_resolver_preserves_specific_target_with_parent_context(
    signal_type: str,
    raw_value: str,
    display_name: str,
) -> None:
    calls: list[dict[str, object]] = []

    class _FakeNominatim:
        @staticmethod
        def normalize_component(value: str) -> str:
            decomposed = unicodedata.normalize("NFKD", value)
            return " ".join(
                decomposed.encode("ascii", "ignore").decode("ascii").lower().split()
            )

        async def extract_coordinates(
            self,
            *,
            address: str,
            city: str | None,
            country_name: str | None,
            country_code: str | None,
            expected_location_type: str | None = None,
        ) -> dict[str, object] | None:
            calls.append(
                {
                    "address": address,
                    "city": city,
                    "country_name": country_name,
                    "country_code": country_code,
                    "expected_location_type": expected_location_type,
                }
            )
            return {
                "display_name": display_name,
                "lat": 48.1,
                "lon": 11.5,
                "selected_result_type": "city" if signal_type == "city" else "station",
                "selected_result_class": "place" if signal_type == "city" else "railway",
                "address": {
                    "city": "München" if "München" in display_name else "Metro City",
                    "country": "Deutschland" if "Deutschland" in display_name else "Brasil" if "Brasil" in display_name else "Countryland",
                },
            }

    resolver = LocationResolver(nominatim_service=_FakeNominatim())
    parents = [
        LocationSignal(
            signal_type="country",
            raw_value="Deutschland" if "Deutschland" in display_name else "Brasil" if "Brasil" in display_name else "Countryland",
            confidence=0.99,
        )
    ]
    if signal_type == "address":
        parents.insert(
            0,
            LocationSignal(
                signal_type="city",
                raw_value="Metro City",
                confidence=0.2,
            ),
        )

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                *parents,
                LocationSignal(
                    signal_type=signal_type, raw_value=raw_value, confidence=0.1
                ),
            ],
            {},
        )
        assert result.label == display_name
        assert result.location_type == ("city" if signal_type == "city" else "station")

    run_async_in_thread(_run())
    assert calls
    assert calls[0]["expected_location_type"] == signal_type
    assert calls[0]["country_name"] is not None
    if signal_type == "address":
        assert calls[0]["city"] == "Metro City"


###############################################################################
def test_location_resolver_accepts_compound_city_signal_from_city_boundary() -> None:
    class _CityBoundary:
        async def extract_coordinates(self, **kwargs):  # noqa: ANN003, ANN201
            return {
                "display_name": "Harborview, Coastal Province, Republicland",
                "lat": 12.3,
                "lon": 45.6,
                "selected_result_type": "administrative",
                "selected_result_class": "administrative",
                "address": {
                    "city": "Harborview",
                    "state": "Coastal Province",
                    "country": "Republicland",
                },
            }

    resolver = LocationResolver(nominatim_service=_CityBoundary())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                LocationSignal(
                    signal_type="city",
                    raw_value="Harborview, Republicland",
                    normalized_value="Harborview, Republicland",
                )
            ],
            {},
        )
        assert result.label.startswith("Harborview")
        assert result.location_type == "city"
        assert result.city == "Harborview"

    run_async_in_thread(_run())


###############################################################################
def test_location_resolver_rejects_parent_only_geocoder_result() -> None:
    class _ParentOnly:
        async def extract_coordinates(self, **kwargs):  # noqa: ANN003, ANN201
            return {
                "display_name": "Example City, Example Country",
                "lat": 10.0,
                "lon": 20.0,
                "selected_result_type": "country",
                "selected_result_class": "boundary",
            }

    resolver = LocationResolver(nominatim_service=_ParentOnly())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [LocationSignal(signal_type="city", raw_value="Example City")], {}
        )
        assert result.missing_fields == ["location"]
        assert "safely resolve" in result.question

    run_async_in_thread(_run())


###############################################################################
def test_location_resolver_clarifies_conflicting_parent_context() -> None:
    class _ShouldNotGeocode:
        async def extract_coordinates(self, **kwargs):  # noqa: ANN003, ANN201
            raise AssertionError("conflicting parents must be rejected before lookup")

    resolver = LocationResolver(nominatim_service=_ShouldNotGeocode())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                LocationSignal(signal_type="city", raw_value="Springfield"),
                LocationSignal(signal_type="country", raw_value="Freedonia"),
                LocationSignal(signal_type="country", raw_value="Sylvania"),
            ],
            {},
        )
        assert result.missing_fields == ["location"]
        assert "conflicting" in result.reason

    run_async_in_thread(_run())


###############################################################################
def test_location_resolver_clarifies_same_level_targets() -> None:
    resolver = LocationResolver(nominatim_service=None)

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                LocationSignal(signal_type="city", raw_value="Springfield"),
                LocationSignal(signal_type="city", raw_value="Shelbyville"),
            ],
            {},
        )
        assert result.missing_fields == ["location"]
        assert "Springfield" in result.question
        assert "Shelbyville" in result.question

    run_async_in_thread(_run())


###############################################################################
@pytest.mark.parametrize(
    "response",
    [None, {}, {"lat": "not-a-number", "lon": 10.0}],
)
def test_location_resolver_clarifies_empty_or_malformed_geocoder_response(
    response: dict[str, object] | None,
) -> None:
    class _Malformed:
        async def extract_coordinates(self, **kwargs):  # noqa: ANN003, ANN201
            return response

    resolver = LocationResolver(nominatim_service=_Malformed())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [LocationSignal(signal_type="city", raw_value="Example City")], {}
        )
        assert result.missing_fields == ["location"]

    run_async_in_thread(_run())


###############################################################################
def test_location_resolver_surfaces_geocoder_same_level_ambiguity() -> None:
    class _Ambiguous:
        async def extract_coordinates(self, **kwargs):  # noqa: ANN003, ANN201
            return {
                "display_name": "Springfield, North",
                "lat": 1.0,
                "lon": 2.0,
                "selected_result_type": "city",
                "ambiguous_candidates": [
                    {"display_name": "Springfield, North"},
                    {"display_name": "Springfield, South"},
                ],
            }

    resolver = LocationResolver(nominatim_service=_Ambiguous())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [LocationSignal(signal_type="city", raw_value="Springfield")], {}
        )
        assert result.missing_fields == ["location"]
        assert "North" in result.question and "South" in result.question

    run_async_in_thread(_run())


###############################################################################
def test_location_resolver_accepts_localized_named_poi_with_generic_descriptor() -> None:
    class _LocalizedPoi:
        async def extract_coordinates(self, **kwargs):  # noqa: ANN003, ANN201
            return {
                "display_name": "Centre de recherche du port, Port Azure, Pays Exemple",
                "namedetails": {"name:en": "North Harbor Research Center"},
                "lat": 20.0,
                "lon": 30.0,
                "selected_result_type": "attraction",
                "selected_result_class": "tourism",
                "address": {"city": "Port Azure", "country": "Exampleland"},
            }

    resolver = LocationResolver(nominatim_service=_LocalizedPoi())

    async def _run() -> None:
        result = await resolver.resolve_location_signals(
            [
                LocationSignal(
                    signal_type="poi",
                    raw_value="North Harbor Research Center facility",
                    normalized_value="North Harbor Research Center facility",
                ),
                LocationSignal(signal_type="city", raw_value="Port Azure"),
                LocationSignal(signal_type="country", raw_value="Exampleland"),
            ],
            {},
        )
        assert result.label.startswith("Centre de recherche")
        assert result.location_type == "attraction"

    run_async_in_thread(_run())
