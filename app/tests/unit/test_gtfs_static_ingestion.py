from __future__ import annotations

import asyncio
import io
import zipfile

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.gtfs_static import GTFSStaticProvider


def _sample_gtfs_static_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\ns1,Central,41.9,12.5\n")
        archive.writestr("routes.txt", "route_id,route_short_name,route_long_name,route_type\nr1,10,Central Loop,3\n")
        archive.writestr("agency.txt", "agency_id,agency_name,agency_url,agency_timezone\na1,Metro Test,https://example.test,Europe/Rome\n")
        archive.writestr("calendar.txt", "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nwk,1,1,1,1,1,0,0,20260101,20261231\n")
        archive.writestr("shapes.txt", "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nsh1,41.9,12.5,1\nsh1,42.0,12.6,2\n")
    return buffer.getvalue()


def test_gtfs_static_ingestion_parses_core_feed_tables() -> None:
    response = asyncio.run(
        GTFSStaticProvider().fetch(
            ProviderRequest(
                capability_id="gtfs_static",
                params={"feed_bytes": _sample_gtfs_static_zip()},
            )
        )
    )

    assert response.payload["stops"][0]["id"] == "s1"
    assert response.payload["routes"][0]["id"] == "r1"
    assert response.payload["agency"][0]["timezone"] == "Europe/Rome"
    assert response.payload["calendar"][0]["serviceId"] == "wk"
    assert response.payload["shapes"][0]["geometry"]["type"] == "LineString"


def test_gtfs_static_provider_fetches_configured_feed_url() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers: dict[str, str] | None = None) -> bytes:
        calls.append(url)
        return _sample_gtfs_static_zip()

    response = asyncio.run(
        GTFSStaticProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="gtfs_static",
                params={"feed_url": "https://agency.example/gtfs.zip"},
            )
        )
    )

    assert calls == ["https://agency.example/gtfs.zip"]
    assert response.payload["feedUrl"] == "https://agency.example/gtfs.zip"
    assert response.payload["summary"]["stopCount"] == 1
