from __future__ import annotations

from dataclasses import replace
from math import isfinite

from server.common.typing import is_json_array, is_json_object

import argparse
import asyncio
import json
import os
import re
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

ROME_BBOX = (12.45, 41.88, 12.55, 41.93)
NYC_BBOX = (-74.1, 40.6, -73.7, 40.9)

# Keep this tuple as the single smoke-matrix declaration. Every provider
# factory entry must have exactly one case; the unit test enforces that
# invariant against PROVIDER_FACTORIES.
PROVIDER_SMOKE_CHECKS = (
    LiveCheck(
        provider_id="arcgis",
        access_mode="configuration_dependent",
        skip_message="ArcGIS smoke validation requires a caller-supplied FeatureServer URL.",
    ),
    LiveCheck(
        provider_id="census",
        request=ProviderRequest(
            capability_id="census_cartographic_boundaries",
            bbox=NYC_BBOX,
            params={"live": True},
        ),
        response_contract="feature_collection",
        required_payload_keys=("features",),
        required_feature_count=1,
    ),
    LiveCheck(
        provider_id="gibs",
        request=ProviderRequest(
            capability_id="gibs_layer_discovery",
            params={"layer_id": "MODIS_Terra_NDVI_8Day"},
        ),
        response_contract="metadata",
        required_payload_keys=("layer", "render"),
    ),
    LiveCheck(
        provider_id="eea",
        access_mode="configuration_dependent",
        skip_message="EEA smoke validation requires a catalog-supplied WMS URL.",
    ),
    LiveCheck(
        provider_id="esa",
        access_mode="configuration_dependent",
        skip_message="ESA smoke validation requires a catalog-supplied WMTS URL.",
    ),
    LiveCheck(
        provider_id="eurostat",
        access_mode="configuration_dependent",
        skip_message="Eurostat smoke validation requires a catalog-supplied dataset URL.",
    ),
    LiveCheck(
        provider_id="gbif",
        request=ProviderRequest(
            capability_id="gbif_species_occurrences",
            bbox=ROME_BBOX,
            params={"limit": 5},
        ),
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="rainviewer",
        request=ProviderRequest(
            capability_id="rainviewer_precipitation_radar",
        ),
        response_contract="raster_metadata",
        required_payload_keys=("tileUrl", "latestTime", "frameCount"),
        numeric_payload_keys=("frameCount",),
        required_feature_count=1,
    ),
    LiveCheck(
        provider_id="openmeteo",
        request=ProviderRequest(
            capability_id="openmeteo_weather_forecast",
            bbox=ROME_BBOX,
        ),
        response_contract="json_object",
        required_payload_keys=("latitude", "longitude", "current"),
        numeric_payload_keys=("latitude", "longitude"),
        required_feature_count=1,
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
        response_contract="feature_collection",
        required_payload_keys=("features",),
        required_feature_count=1,
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
        access_mode="credentialed",
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="pvgis",
        request=ProviderRequest(
            capability_id="pvgis_solar_potential",
            bbox=ROME_BBOX,
        ),
        response_contract="json_object",
        required_payload_keys=("yearlyKwhPerKwpEstimate",),
        numeric_payload_keys=("latitude", "longitude", "yearlyKwhPerKwpEstimate"),
    ),
    LiveCheck(
        provider_id="tomtom",
        request=ProviderRequest(
            capability_id="tomtom_incidents",
            bbox=ROME_BBOX,
            params={"incidents": True},
        ),
        access_mode="credentialed",
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="windy_webcams",
        request=ProviderRequest(
            capability_id="windy_webcams",
            bbox=ROME_BBOX,
            params={"live": True},
        ),
        access_mode="credentialed",
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="usgs",
        request=ProviderRequest(
            capability_id="usgs_earthquakes",
            bbox=ROME_BBOX,
            params={"live": True, "feed": "all_day"},
        ),
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="noaa",
        request=ProviderRequest(
            capability_id="noaa_weather_alerts",
            bbox=ROME_BBOX,
            params={"live": True},
        ),
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="fema",
        request=ProviderRequest(
            capability_id="fema_nfhl_flood_zones",
            bbox=NYC_BBOX,
        ),
        response_contract="raster_metadata",
        required_payload_keys=("tileUrl", "layer"),
    ),
    LiveCheck(
        provider_id="nasa_firms",
        request=ProviderRequest(
            capability_id="nasa_firms_active_fires",
            bbox=(12.0, 41.5, 13.0, 42.2),
            params={"live": True},
        ),
        access_mode="credentialed",
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="soilgrids",
        request=ProviderRequest(
            capability_id="soilgrids_soil_properties",
            bbox=ROME_BBOX,
            params={"property": "phh2o", "depth": "0-5cm", "quantile": "mean"},
        ),
        response_contract="raster_metadata",
        required_payload_keys=("serviceUrl", "coverageId", "coverageDownloadUrl"),
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
        access_mode="credentialed",
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="openchargemap",
        request=ProviderRequest(
            capability_id="openchargemap_ev_charging",
            bbox=ROME_BBOX,
            params={"live": True},
        ),
        access_mode="credential_or_local_source",
        source_env="AEGIS_OCM_SNAPSHOT_PATH",
        source_path_only=True,
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="ourairports",
        request=ProviderRequest(capability_id="ourairports_airports"),
        response_contract="dataset",
        required_payload_keys=("type", "status", "downloadUrl"),
    ),
    LiveCheck(
        provider_id="gtfs_static",
        request=ProviderRequest(
            capability_id="gtfs_static",
            params={},
        ),
        access_mode="configured_source",
        source_env="AEGIS_GTFS_STATIC_FEED_URL",
        request_env=(("feed_url", "AEGIS_GTFS_STATIC_FEED_URL"),),
        response_contract="dataset",
        required_payload_keys=("stops", "routes", "summary"),
    ),
    LiveCheck(
        provider_id="gtfs_realtime",
        request=ProviderRequest(
            capability_id="gtfs_realtime",
            params={},
        ),
        access_mode="configured_source",
        source_env="AEGIS_GTFS_REALTIME_FEED_URL",
        request_env=(("feed_url", "AEGIS_GTFS_REALTIME_FEED_URL"),),
        response_contract="dataset",
        required_payload_keys=("entities",),
    ),
    LiveCheck(
        provider_id="natural_earth",
        request=ProviderRequest(capability_id="natural_earth_admin_boundaries"),
        response_contract="dataset",
        required_payload_keys=("type", "status", "downloadUrl"),
    ),
    LiveCheck(
        provider_id="overture",
        request=ProviderRequest(
            capability_id="overture_maps_places",
            bbox=ROME_BBOX,
            params={"limit": 10},
        ),
        access_mode="configured_source",
        source_env="AEGIS_OVERTURE_PLACES_INDEX",
        source_path_only=True,
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="openaddresses",
        request=ProviderRequest(capability_id="openaddresses_points"),
        response_contract="dataset",
        required_payload_keys=("type", "status", "downloadUrl"),
    ),
    LiveCheck(
        provider_id="local_open_data",
        request=ProviderRequest(
            capability_id="local_parcel_template",
            params={"source_id": "local_parcel_template"},
        ),
        access_mode="configuration_dependent",
        source_env="LOCAL_OPEN_DATA_SOURCES",
        response_contract="feature_collection",
        required_payload_keys=("features",),
    ),
    LiveCheck(
        provider_id="mobility_database",
        request=ProviderRequest(
            capability_id="mobility_database_feeds",
            bbox=(-74.1, 40.6, -73.7, 40.9),
            params={"query": "MTA", "limit": 10},
        ),
        response_contract="dataset",
        required_payload_keys=("feeds", "catalogRecordCount"),
        numeric_payload_keys=("catalogRecordCount",),
    ),
    LiveCheck(
        provider_id="nominatim",
        request=ProviderRequest(
            capability_id="location_to_coordinates",
            params={"query": "Rome, Italy"},
        ),
        response_contract="result_list",
        required_payload_keys=("results", "resultCount"),
        numeric_payload_keys=("resultCount",),
    ),
)

PUBLIC_LIVE_CHECKS = tuple(
    check for check in PROVIDER_SMOKE_CHECKS if check.access_mode == "public"
)
CREDENTIAL_LIVE_CHECKS = tuple(
    check
    for check in PROVIDER_SMOKE_CHECKS
    if check.access_mode in {"credentialed", "credential_or_local_source"}
)

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)(\s*[:=]\s*)[^\s,;}]+"
)

###############################################################################
async def validate_live_geospatial_sources(
    *,
    include_credentialed: bool = False,
    registry_factory: Callable[[], ProviderRegistry] = ProviderRegistry,
    checks: tuple[LiveCheck, ...] | None = None,
) -> LiveValidationReport:
    registry = registry_factory()
    selected_checks = checks or PROVIDER_SMOKE_CHECKS
    report = LiveValidationReport()
    for check in selected_checks:
        result = await _run_check(
            registry,
            check,
            include_credentialed=include_credentialed,
        )
        report.results.append(result)
        if result.status == "failed":
            report.error_count += 1
        elif result.status == "skipped":
            report.skipped_count += 1
    return report

###############################################################################
async def _run_check(
    registry: ProviderRegistry,
    check: LiveCheck,
    *,
    include_credentialed: bool = True,
) -> LiveValidationCheckResult:
    access_mode = _access_mode(check)
    capability_id = _capability_id(check)
    request = check.request

    if request is None:
        return _skipped_result(
            check,
            capability_id,
            check.skip_message or "No universal smoke request is configured.",
        )

    local_source_ready = _source_is_configured(check, request)
    credentials_ready = _credential_is_configured(registry, check.provider_id)
    if access_mode == "credentialed":
        if not include_credentialed:
            return _skipped_result(
                check,
                capability_id,
                "Credentialed smoke checks are disabled.",
            )
        if not credentials_ready:
            return _skipped_result(
                check,
                capability_id,
                f"Missing saved credential for provider '{check.provider_id}'.",
            )
    elif access_mode == "credential_or_local_source":
        if not local_source_ready and not credentials_ready:
            return _skipped_result(
                check,
                capability_id,
                check.skip_message
                or (
                    f"Provider '{check.provider_id}' needs a saved credential "
                    "or configured local source."
                ),
            )
        if credentials_ready and not local_source_ready and not include_credentialed:
            return _skipped_result(
                check,
                capability_id,
                "Credentialed smoke checks are disabled and no local source is configured.",
            )
    elif access_mode in {"configured_source", "configuration_dependent"}:
        if not local_source_ready:
            return _skipped_result(
                check,
                capability_id,
                check.skip_message
                or f"Provider '{check.provider_id}' has no configured source.",
            )

    request = _materialize_request(check, request)
    try:
        response = await registry.fetch(check.provider_id, request)
        count = _feature_count(response.payload)
        validation_error = _validate_payload(check, response.payload)
        if validation_error is not None:
            return _failed_result(
                check,
                capability_id,
                validation_error,
                feature_count=count,
            )
        if (
            check.required_feature_count is not None
            and count < check.required_feature_count
        ):
            return _failed_result(
                check,
                capability_id,
                (
                    f"Expected at least {check.required_feature_count} semantic "
                    f"records; got {count}."
                ),
                feature_count=count,
            )
        return LiveValidationCheckResult(
            provider_id=check.provider_id,
            capability_id=capability_id,
            access_mode=access_mode,
            status="passed",
            feature_count=count,
        )
    except ProviderAuthError:
        return _failed_result(
            check,
            capability_id,
            "Provider rejected the configured credential.",
        )
    except (ProviderError, ProviderRegistryError, TypeError, ValueError) as exc:
        return _failed_result(check, capability_id, _sanitize_message(str(exc)))
    except Exception as exc:  # pragma: no cover - defensive boundary for live runs
        return _failed_result(
            check,
            capability_id,
            f"Unexpected provider failure: {_sanitize_message(str(exc))}",
        )

###############################################################################
def _access_mode(check: LiveCheck) -> str:
    if check.requires_credentials:
        return "credentialed"
    return check.access_mode

###############################################################################
def _capability_id(check: LiveCheck) -> str:
    if check.request is not None:
        return check.request.capability_id
    return f"{check.provider_id}:smoke"

###############################################################################
def _credential_is_configured(registry: ProviderRegistry, provider_id: str) -> bool:
    resolver = getattr(registry, "credential_resolver", None)
    is_configured = getattr(resolver, "is_configured", None)
    if callable(is_configured):
        return bool(is_configured(provider_id))
    provider_credentials_present = getattr(
        registry, "provider_credentials_present", None
    )
    return bool(
        callable(provider_credentials_present)
        and provider_credentials_present(provider_id)
    )

###############################################################################
def _source_is_configured(check: LiveCheck, request: ProviderRequest) -> bool:
    if check.source_env is None:
        if isinstance(request.params.get("feed_bytes"), bytes):
            return True
        for key in ("snapshot_path", "index_path", "source_path"):
            value = str(request.params.get(key) or "").strip()
            if value and Path(value).expanduser().is_file():
                return True
        for key in ("feed_url", "source_url"):
            value = str(request.params.get(key) or "").strip()
            if value.startswith(("http://", "https://")):
                return True
            if value and Path(value).expanduser().is_file():
                return True
        return False
    raw_value = os.getenv(check.source_env, "").strip()
    if check.source_env == "LOCAL_OPEN_DATA_SOURCES":
        if not raw_value:
            return False
        try:
            sources = json.loads(raw_value)
        except json.JSONDecodeError:
            return False
        if not is_json_object(sources):
            return False
        source_id = str(request.params.get("source_id") or request.capability_id)
        return bool(str(sources.get(source_id) or "").strip())
    if not raw_value:
        return False
    if check.source_path_only:
        return Path(raw_value).expanduser().is_file()
    if raw_value.startswith(("http://", "https://")):
        return True
    return Path(raw_value).expanduser().is_file()

###############################################################################
def _materialize_request(
    check: LiveCheck, request: ProviderRequest
) -> ProviderRequest:
    if not check.request_env:
        return request
    params = dict(request.params)
    for parameter, env_name in check.request_env:
        value = os.getenv(env_name, "").strip()
        if value:
            params[parameter] = value
    return replace(request, params=params)

###############################################################################
def _skipped_result(
    check: LiveCheck, capability_id: str, message: str
) -> LiveValidationCheckResult:
    return LiveValidationCheckResult(
        provider_id=check.provider_id,
        capability_id=capability_id,
        access_mode=_access_mode(check),
        status="skipped",
        message=_sanitize_message(message),
    )

###############################################################################
def _failed_result(
    check: LiveCheck,
    capability_id: str,
    message: str,
    *,
    feature_count: int | None = None,
) -> LiveValidationCheckResult:
    return LiveValidationCheckResult(
        provider_id=check.provider_id,
        capability_id=capability_id,
        access_mode=_access_mode(check),
        status="failed",
        message=_sanitize_message(message),
        feature_count=feature_count,
    )

###############################################################################
def _validate_payload(
    check: LiveCheck, payload: object
) -> str | None:
    if not is_json_object(payload):
        return "Provider response payload must be a JSON object."
    if payload.get("error"):
        return (
            "Provider returned an error payload: "
            f"{_sanitize_message(str(payload.get('error')))}"
        )
    if str(payload.get("status") or "").strip().casefold() in {
        "error",
        "failed",
    }:
        return "Provider returned an error status."
    for key in check.required_payload_keys:
        if key not in payload:
            return f"Provider response is missing required field '{key}'."
    for key in check.numeric_payload_keys:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return f"Provider response field '{key}' must be numeric."
        if not isfinite(float(value)):
            return f"Provider response field '{key}' must be finite."

    contract = check.response_contract
    if contract == "feature_collection":
        return _validate_feature_collection(payload)
    if contract == "result_list":
        return _validate_result_list(payload)
    if contract == "raster_metadata":
        return _validate_raster_metadata(payload)
    if contract == "dataset":
        return _validate_dataset(payload)
    if contract == "metadata" and not payload:
        return "Provider metadata payload must not be empty."
    if contract == "json_object" and not payload:
        return "Provider JSON payload must not be empty."
    return None

###############################################################################
def _validate_feature_collection(payload: dict[str, Any]) -> str | None:
    features = payload.get("features")
    if not is_json_array(features):
        return "Provider response is missing a feature array."
    for feature in features:
        if not is_json_object(feature) or not _has_feature_geometry(feature):
            return "Provider response contains a feature without valid geometry."
    return None

###############################################################################
def _validate_result_list(payload: dict[str, Any]) -> str | None:
    results = payload.get("results")
    if not is_json_array(results):
        return "Provider response is missing a result array."
    for result in results:
        if not is_json_object(result) or not _has_feature_geometry(result):
            return "Provider response contains a result without valid coordinates."
    return None

###############################################################################
def _has_feature_geometry(feature: dict[str, Any]) -> bool:
    latitude = feature.get("latitude")
    longitude = feature.get("longitude")
    if _valid_coordinate_pair(latitude, longitude):
        return True
    geometry = feature.get("geometry")
    if not is_json_object(geometry):
        return False
    return _valid_coordinates(geometry.get("coordinates"))

###############################################################################
def _valid_coordinate_pair(latitude: object, longitude: object) -> bool:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return False
    if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
        return False
    return (
        isfinite(float(latitude))
        and isfinite(float(longitude))
        and -90.0 <= float(latitude) <= 90.0
        and -180.0 <= float(longitude) <= 180.0
    )

###############################################################################
def _valid_coordinates(value: object) -> bool:
    if not is_json_array(value):
        return False
    if len(value) >= 2 and _valid_coordinate_pair(value[1], value[0]):
        return True
    return any(_valid_coordinates(item) for item in value)

###############################################################################
def _validate_raster_metadata(payload: dict[str, Any]) -> str | None:
    url_keys = ("tileUrl", "tile_url", "serviceUrl", "coverageDownloadUrl")
    if not any(
        isinstance(payload.get(key), str) and payload[key].strip()
        for key in url_keys
    ):
        return "Raster response is missing a usable service or tile URL."
    return None

###############################################################################
def _validate_dataset(payload: dict[str, Any]) -> str | None:
    if not any(
        key in payload
        for key in ("type", "status", "downloadUrl", "feeds", "entities", "summary")
    ):
        return "Dataset response is missing its declared structure."
    return None

###############################################################################
def _feature_count(payload: dict[str, Any]) -> int:
    for key in ("features", "results", "feeds", "series", "entities"):
        if is_json_array(payload.get(key)):
            return len(payload[key])
    summary = payload.get("summary")
    if is_json_object(summary):
        for key in ("vehicleCount", "alertCount", "stopCount", "routeCount"):
            value = summary.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    if isinstance(payload.get("frameCount"), int) and not isinstance(
        payload["frameCount"], bool
    ):
        return payload["frameCount"]
    if isinstance(payload.get("yearlyKwhPerKwpEstimate"), int | float):
        return 1
    return 0

###############################################################################
def _sanitize_message(message: str) -> str:
    return _SECRET_PATTERN.sub(r"\1=<redacted>", message)

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
