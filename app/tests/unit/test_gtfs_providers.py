from __future__ import annotations

import asyncio
import io
import zipfile

import pytest

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider
from server.services.geospatial.providers.gtfs_static import GTFSStaticProvider


def _gtfs_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon\ns1,Central,41.9,12.5\n",
        )
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name,route_type\nr1,10,Central Loop,3\n",
        )
        archive.writestr(
            "shapes.txt",
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nsh1,41.9,12.5,1\n",
        )
    return buffer.getvalue()


def test_gtfs_static_provider_normalizes_stops_routes_and_shapes() -> None:
    response = asyncio.run(
        GTFSStaticProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_static",
                params={"feed_bytes": _gtfs_zip()},
            )
        )
    )

    assert response.payload["renderingMode"] == "clustered-points"
    assert response.payload["stops"][0]["name"] == "Central"
    assert response.payload["routes"][0]["shortName"] == "10"
    assert response.payload["summary"]["shapePointCount"] == 1


def test_gtfs_static_provider_rejects_bad_zip() -> None:
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            GTFSStaticProvider().fetch(
                ProviderRequest(
                    capability_id="gtfs_static",
                    params={"feed_bytes": b"not-a-zip"},
                )
            )
        )


def test_gtfs_realtime_provider_normalizes_decoded_feed() -> None:
    response = asyncio.run(
        GTFSRealtimeProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_realtime",
                params={
                    "decoded_feed": {
                        "header": {"timestamp": 1778486400},
                        "entities": [
                            {
                                "vehicle": {
                                    "id": "v1",
                                    "tripId": "t1",
                                    "routeId": "r1",
                                    "position": {
                                        "latitude": 41.9,
                                        "longitude": 12.5,
                                    },
                                }
                            },
                            {"alert": {"effect": "DETOUR"}},
                            {"tripUpdate": {"tripId": "t2"}},
                        ],
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "clustered-points"
    assert response.payload["vehicles"][0]["id"] == "v1"
    assert response.payload["summary"] == {
        "vehicleCount": 1,
        "alertCount": 1,
        "tripUpdateCount": 1,
    }
    assert response.payload["feedTimestamp"]


def test_provider_registry_binds_gtfs_adapters_from_manifests() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    assert "gtfs_static" in registry.list_provider_ids()
    assert "gtfs_realtime" in registry.list_provider_ids()
