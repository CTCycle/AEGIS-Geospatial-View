from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.overture import OvertureProvider

###############################################################################
def test_openchargemap_infrastructure_source_normalizes_live_station() -> None:
    async def fetcher(url, headers):
        del url, headers
        return [
            {
                "ID": 1,
                "AddressInfo": {
                    "Title": "Fast Charge",
                    "Latitude": 41.9,
                    "Longitude": 12.5,
                    "AddressLine1": "1 Main St",
                },
            }
        ]

    response = run_async_in_thread(
        OpenChargeMapProvider(api_key="ocm-key", fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5, "live": True},
            )
        )
    )

    assert response.payload["features"][0]["category"] == "ev_charging"
    assert response.payload["features"][0]["source"] == "openchargemap"

###############################################################################
def test_overture_maps_queries_ingested_places_index(tmp_path) -> None:
    index = tmp_path / "places.geojson"
    index.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"p1","properties":{"name":"Clinic","category":"healthcare"},"geometry":{"type":"Point","coordinates":[12.5,41.9]}}]}',
        encoding="utf-8",
    )
    response = run_async_in_thread(
        OvertureProvider(places_path=index).fetch(
            ProviderRequest(capability_id="overture_maps_places", bbox=(12, 41, 13, 42))
        )
    )

    assert response.payload["features"][0]["source"] == "overture"
    assert response.payload["totalResults"] == 1

###############################################################################
def test_overture_maps_can_augment_local_places_with_overpass_and_deduplicate(tmp_path) -> None:
    index = tmp_path / "places.geojson"
    index.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","id":"overture-1","properties":{"name":"Cafe Roma","category":"cafe"},"geometry":{"type":"Point","coordinates":[12.5,41.9]}}]}',
        encoding="utf-8",
    )

    ###############################################################################
    class _FakeOverpass:
        default_radius_m = 500.0

        # -------------------------------------------------------------------------
        async def get_nearby_poi(self, **kwargs):  # noqa: ANN003
            assert kwargs["latitude"] == 41.9
            assert kwargs["longitude"] == 12.5
            return {
                "items": [
                    {
                        "id": "node-1",
                        "name": "Cafe Roma",
                        "amenity": "cafe",
                        "latitude": 41.9,
                        "longitude": 12.5,
                    }
                ]
            }

    response = run_async_in_thread(
        OvertureProvider(places_path=index, overpass_service=_FakeOverpass()).fetch(
            ProviderRequest(
                capability_id="overture_maps_places",
                bbox=(12, 41, 13, 42),
                params={
                    "augment_overpass": True,
                    "latitude": 41.9,
                    "longitude": 12.5,
                },
            )
        )
    )

    assert response.payload["augmentation"] == "overpass"
    assert response.payload["totalResults"] == 1
    assert "© OpenStreetMap contributors (ODbL)" in response.attribution
