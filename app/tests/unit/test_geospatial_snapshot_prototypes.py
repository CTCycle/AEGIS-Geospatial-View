from __future__ import annotations

import asyncio
import json

from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest
from server.services.geospatial.providers.nrel import NRELProvider
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider

###############################################################################
def test_openchargemap_requires_key_for_hosted_access() -> None:
    try:
        asyncio.run(
            OpenChargeMapProvider().fetch(
                ProviderRequest(
                    capability_id="openchargemap_ev_charging",
                    params={"latitude": 41.9, "longitude": 12.5, "live": True},
                )
            )
        )
    except ProviderAuthError as exc:
        assert "OPENCHARGEMAP_API_KEY" in str(exc)
    else:
        raise AssertionError("Hosted Open Charge Map access must not be anonymous.")

###############################################################################
def test_openchargemap_reads_local_snapshot(tmp_path) -> None:
    snapshot = tmp_path / "ocm.json"
    snapshot.write_text(
        json.dumps([{"ID": 1, "AddressInfo": {"Title": "Charger", "Latitude": 41.9, "Longitude": 12.5}}]),
        encoding="utf-8",
    )
    response = asyncio.run(
        OpenChargeMapProvider(snapshot_path=snapshot).fetch(
            ProviderRequest(capability_id="openchargemap_ev_charging", params={"live": True, "latitude": 41.9, "longitude": 12.5})
        )
    )
    assert response.payload["sourceMode"] == "local-snapshot"
    assert response.payload["featureCount"] == 1

###############################################################################
def test_afdc_reads_local_csv_snapshot_without_hosted_key(tmp_path) -> None:
    snapshot = tmp_path / "afdc.csv"
    snapshot.write_text(
        "id,station_name,latitude,longitude,fuel_type_code\n1,Station,41.9,12.5,ELEC\n",
        encoding="utf-8",
    )
    response = asyncio.run(
        NRELProvider(snapshot_path=snapshot).fetch(
            ProviderRequest(capability_id="nrel_afdc_alt_fuel_stations", params={"live": True, "latitude": 41.9, "longitude": 12.5})
        )
    )
    assert response.payload["sourceMode"] == "local-snapshot"
    assert response.payload["features"][0]["category"] == "ev_charging"
