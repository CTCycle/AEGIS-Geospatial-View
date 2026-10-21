"""Recheck optional formats, configured-source eligibility, and public GTFS feeds."""

import asyncio
import importlib.util
import json
import os
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider
from server.services.geospatial.providers.gtfs_static import GTFSStaticProvider
from server.services.geospatial.live_validator import PROVIDER_SMOKE_CHECKS, validate_live_geospatial_sources
from server.services.geospatial.provider_registry import ProviderRegistry


###############################################################################
async def probe(provider, capability, url):
    try:
        result = await asyncio.wait_for(provider.fetch(ProviderRequest(
            capability_id=capability, params={"feed_url": url},
        )), timeout=45)
        payload = result.payload
        return {
            "status": "PASS" if any(payload.get("summary", {}).values()) else "PARTIAL",
            "url": url, "summary": payload.get("summary"),
            "renderingMode": payload.get("renderingMode"),
            "feedTimestamp": payload.get("feedTimestamp"),
            "vehicleRenderingAllowed": payload.get("vehicleRenderingAllowed"),
            "attribution": result.attribution,
        }
    except Exception as exc:
        return {"status": "BLOCKED", "url": url, "error_type": type(exc).__name__, "message": str(exc)[:200]}


###############################################################################
async def main():
    with urllib.request.urlopen("http://127.0.0.1:5079/api/geospatial/capabilities") as response:
        catalog = json.load(response)
    ids = {"gtfs_static", "gtfs_realtime", "local_parcel_template", "overture_maps_places", "openchargemap_ev_charging", "openmeteo_elevation", "census_tigerweb_demographics", "eea_noise_2019"}
    capabilities = [
        {key: item.get(key) for key in ("id", "is_available", "availability_reason", "endpoint_health", "reliability")}
        for item in catalog["capabilities"] if item.get("id") in ids
    ]
    static, realtime = await asyncio.gather(
        probe(GTFSStaticProvider(), "gtfs_static", "https://www.bart.gov/sites/default/files/2026-08/google_transit_20260810-20270108_v02.zip"),
        probe(GTFSRealtimeProvider(), "gtfs_realtime", "https://cdn.mbta.com/realtime/VehiclePositions.pb"),
    )
    os.environ["AEGIS_GTFS_STATIC_FEED_URL"] = static["url"]
    os.environ["AEGIS_GTFS_REALTIME_FEED_URL"] = realtime["url"]
    configured = await validate_live_geospatial_sources(
        checks=tuple(check for check in PROVIDER_SMOKE_CHECKS if check.provider_id in {"gtfs_static", "gtfs_realtime"}),
        registry_factory=lambda: ProviderRegistry(providers=[GTFSStaticProvider(), GTFSRealtimeProvider()]),
    )
    result = {
        "date": datetime.now(UTC).isoformat(),
        "optional_modules": {name: importlib.util.find_spec(name) is not None for name in (
            "geopandas", "rasterio", "pyogrio", "duckdb", "rtree",
        )},
        "configured_source_catalog": capabilities,
        "static": static, "realtime": realtime,
        "configured_live_validator": configured.model_dump(mode="json"),
        "static_url_resolution": "BART's /dev/schedules/google_transit.zip returned HTTP 307 to the dated official same-host archive used here. Production transport rejects redirects by design.",
        "boundary": "Direct production-adapter feed probes; browser rendering and full agent route are separate.",
    }
    output = Path(__file__).resolve().with_name("partial-ingestion-probe.json")
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


asyncio.run(main())
