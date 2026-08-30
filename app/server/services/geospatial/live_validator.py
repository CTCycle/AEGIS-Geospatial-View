from __future__ import annotations

from server.common.typing import is_json_array, is_json_object

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from server.domain.geospatial.providers import ProviderRequest
from server.domain.geospatial.registry import (
    LiveCheck,
    LiveValidationCheckResult,
    LiveValidationReport,
)
from server.services.geospatial.provider_registry import (
    ProviderRegistry,
    ProviderRegistryError,
)
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderError,
)

PUBLIC_LIVE_CHECKS = (
    LiveCheck(
        provider_id="nominatim",
        request=ProviderRequest(
            capability_id="location_to_coordinates",
            params={"query": "Rome, Italy"},
        ),
    ),
    LiveCheck(
        provider_id="usgs",
        request=ProviderRequest(
            capability_id="usgs_earthquakes",
            params={"live": True, "feed": "all_day"},
        ),
    ),
    LiveCheck(
        provider_id="openmeteo",
        request=ProviderRequest(
            capability_id="openmeteo_weather_forecast",
            bbox=(12.45, 41.88, 12.55, 41.92),
        ),
    ),
    LiveCheck(
        provider_id="overpass",
        request=ProviderRequest(
            capability_id="get_nearby_poi",
            params={
                "latitude": 41.9028,
                "longitude": 12.4964,
                "radius_m": 250,
                "amenity_tags": ["cafe"],
                "limit": 3,
            },
        ),
        required_feature_count=1,
    ),
    LiveCheck(
        provider_id="rainviewer",
        request=ProviderRequest(
            capability_id="rainviewer_precipitation_radar",
        ),
        required_feature_count=1,
    ),
    LiveCheck(
        provider_id="pvgis",
        request=ProviderRequest(
            capability_id="pvgis_solar_potential",
            bbox=(12.45, 41.88, 12.55, 41.93),
        ),
        required_feature_count=1,
    ),
)

CREDENTIAL_LIVE_CHECKS = (
    LiveCheck(
        provider_id="tomtom",
        request=ProviderRequest(
            capability_id="tomtom_incidents",
            bbox=(12.45, 41.88, 12.55, 41.93),
            params={"incidents": True},
        ),
        credential_env="TOMTOM_API_KEY",
    ),
    LiveCheck(
        provider_id="opentripmap",
        request=ProviderRequest(
            capability_id="opentripmap_tourism_pois",
            params={
                "live": True,
                "latitude": 41.9028,
                "longitude": 12.4964,
                "radius_m": 2500,
                "kinds": "interesting_places",
                "limit": 10,
            },
        ),
        credential_env="OPENTRIPMAP_API_KEY",
    ),
    LiveCheck(
        provider_id="windy_webcams",
        request=ProviderRequest(
            capability_id="windy_webcams",
            bbox=(12.45, 41.88, 12.55, 41.92),
            params={"live": True},
        ),
        credential_env="WINDY_WEBCAMS_API_KEY",
    ),
    LiveCheck(
        provider_id="openaq",
        request=ProviderRequest(
            capability_id="openaq_air_quality",
            params={
                "live": True,
                "latitude": 41.9028,
                "longitude": 12.4964,
                "radius_m": 25000,
                "pollutants": ["pm25", "pm10", "no2"],
            },
        ),
        credential_env="OPENAQ_API_KEY",
    ),
    LiveCheck(
        provider_id="nasa_firms",
        request=ProviderRequest(
            capability_id="nasa_firms_active_fires",
            bbox=(12.0, 41.5, 13.0, 42.2),
            params={"live": True},
        ),
        credential_env="NASA_API_KEY",
    ),
    LiveCheck(
        provider_id="mobility_database",
        request=ProviderRequest(
            capability_id="mobility_database_feeds",
            bbox=(-74.1, 40.6, -73.7, 40.9),
            params={"query": "MTA", "limit": 10},
        ),
    ),
)


###############################################################################
async def validate_live_geospatial_sources(
    *,
    include_credentialed: bool = False,
    registry_factory: Callable[[], ProviderRegistry] = ProviderRegistry,
) -> LiveValidationReport:
    registry = registry_factory()
    registry.build_from_manifests()
    checks = list(PUBLIC_LIVE_CHECKS)
    if include_credentialed:
        checks.extend(CREDENTIAL_LIVE_CHECKS)
    report = LiveValidationReport()
    for check in checks:
        result = await _run_check(registry, check)
        report.results.append(result)
        if result.status == "failed":
            report.error_count += 1
        if result.status == "skipped":
            report.skipped_count += 1
    return report


###############################################################################
async def _run_check(
    registry: ProviderRegistry, check: LiveCheck
) -> LiveValidationCheckResult:
    if check.credential_env and not os.getenv(check.credential_env, "").strip():
        return LiveValidationCheckResult(
            provider_id=check.provider_id,
            capability_id=check.request.capability_id,
            status="skipped",
            message=f"Missing optional credential environment variable {check.credential_env}.",
        )
    try:
        response = await registry.fetch(check.provider_id, check.request)
        count = _feature_count(response.payload)
        payload_error = response.payload.get("error")
        if payload_error:
            return LiveValidationCheckResult(
                provider_id=check.provider_id,
                capability_id=check.request.capability_id,
                status="failed",
                message=f"Provider returned an error payload: {payload_error}",
                feature_count=count,
            )
        if (
            check.required_feature_count is not None
            and count < check.required_feature_count
        ):
            return LiveValidationCheckResult(
                provider_id=check.provider_id,
                capability_id=check.request.capability_id,
                status="failed",
                message=(
                    f"Expected at least {check.required_feature_count} features; got {count}."
                ),
                feature_count=count,
            )
        return LiveValidationCheckResult(
            provider_id=check.provider_id,
            capability_id=check.request.capability_id,
            status="passed",
            feature_count=count,
        )
    except ProviderAuthError as exc:
        return LiveValidationCheckResult(
            provider_id=check.provider_id,
            capability_id=check.request.capability_id,
            status="failed",
            message=str(exc),
        )
    except (ProviderError, ProviderRegistryError, ValueError) as exc:
        return LiveValidationCheckResult(
            provider_id=check.provider_id,
            capability_id=check.request.capability_id,
            status="failed",
            message=str(exc),
        )


###############################################################################
def _feature_count(payload: dict[str, Any]) -> int:
    if is_json_array(payload.get("features")):
        return len(payload["features"])
    if is_json_array(payload.get("results")):
        return len(payload["results"])
    if is_json_array(payload.get("feeds")):
        return len(payload["feeds"])
    if is_json_array(payload.get("series")):
        return len(payload["series"])
    summary = payload.get("summary")
    if is_json_object(summary):
        for key in ("vehicleCount", "alertCount", "stopCount", "routeCount"):
            value = summary.get(key)
            if isinstance(value, int):
                return value
    if isinstance(payload.get("frameCount"), int):
        return payload["frameCount"]
    if payload.get("yearlyKwhPerKwpEstimate") is not None:
        return 1
    return 0


###############################################################################
def _format_report(report: LiveValidationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)


###############################################################################
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate live geospatial providers.")
    parser.add_argument(
        "--include-credentialed",
        action="store_true",
        help="Run checks for credential-gated providers when credentials are configured.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero on live validation failures.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the machine-readable validation report to this path.",
    )
    args = parser.parse_args(argv)
    report = asyncio.run(
        validate_live_geospatial_sources(
            include_credentialed=args.include_credentialed,
        )
    )
    formatted = _format_report(report)
    print(formatted)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted + "\n", encoding="utf-8")
    return 0 if report.ok or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
