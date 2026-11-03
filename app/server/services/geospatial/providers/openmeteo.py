from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

import asyncio
from datetime import UTC, datetime, timedelta
import math
from typing import Any, Literal, cast

from shapely.geometry import Point

from server.configurations.settings import OpenMeteoSettings
from server.services.geospatial.openmeteo import (
    OPENMETEO_AIR_QUALITY_MAX_FORECAST_DAYS,
    OPENMETEO_WEATHER_MAX_FORECAST_DAYS,
    OpenMeteoRateLimitError,
    OpenMeteoRequestError,
    OpenMeteoService,
    OpenMeteoServiceError,
    clip_window_to_forecast_range,
)
from server.services.catalog.loader import find_macro_region_entry
from server.services.geospatial.land_mask import MASK_SOURCE, LandMask, land_mask
from server.services.geospatial.providers._request import request_center, grid_points
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderError,
    ProviderInvalidQueryError,
    ProviderRequest,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderUnavailableError,
    provider_error_for_http_status,
    safe_request_params,
)

ResultStatus = Literal["ok", "valid_empty", "partial", "stale"]

# Land samples per area query (fetched in batches of 100) and coarse cells per
# metric re-sampled at a third of the grid spacing.
WEATHER_GRID_POINT_BUDGET = 300
GRID_REFINEMENT_SEEDS_PER_METRIC = 5

###############################################################################
class OpenMeteoProvider(GeospatialProvider):
    provider_id = "openmeteo"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        service: OpenMeteoService | None = None,
        settings: OpenMeteoSettings | None = None,
    ) -> None:
        self.service = service or OpenMeteoService(settings=settings)

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        if request.params.get("sampling") == "area" and request.bbox is not None and request.capability_id == "openmeteo_weather_forecast":
            return await self._weather_grid(request)
        latitude, longitude = request_center(request)
        now = datetime.now(UTC)
        requested = _requested_window(request, now)
        window: tuple[datetime, datetime] | None = None
        if requested is not None and "elevation" not in request.capability_id:
            # The endpoints only serve a bounded span of dates; anything
            # outside it cannot be requested, and an uncovered remainder is
            # reported as partial coverage below.
            window = clip_window_to_forecast_range(
                requested,
                now,
                max_forecast_days=(
                    OPENMETEO_AIR_QUALITY_MAX_FORECAST_DAYS
                    if "air_quality" in request.capability_id
                    else OPENMETEO_WEATHER_MAX_FORECAST_DAYS
                ),
            )
            if window is None:
                raise ProviderInvalidQueryError(
                    "Open-Meteo serves no hours for the requested window "
                    f"{requested[0].isoformat()} to {requested[1].isoformat()}."
                )
        window_args: dict[str, Any] = {"window": window} if window is not None else {}
        try:
            if "elevation" in request.capability_id:
                payload = await self.service.get_elevation(
                    latitude=latitude,
                    longitude=longitude,
                )
            elif "air_quality" in request.capability_id:
                payload = await self.service.get_air_quality_forecast(
                    latitude=latitude,
                    longitude=longitude,
                    **window_args,
                )
            else:
                payload = await self.service.get_weather_forecast(
                    latitude=latitude,
                    longitude=longitude,
                    **window_args,
                )
        except (OpenMeteoServiceError, ValueError) as exc:
            raise _provider_error(exc) from exc
        payload = dict(payload)
        if not json_object(payload.get("request_parameters")):
            payload["request_parameters"] = safe_request_params(request.params)
        if requested is not None and window is not None:
            payload = _apply_window(payload, requested, window, now)
        rendering_mode = "clustered-points"
        normalized = self._payload(payload, rendering_mode=rendering_mode)
        partial = bool(payload.get("partial"))
        raw_result_status = str(payload.get("result_status") or "").strip()
        if raw_result_status in {"ok", "valid_empty", "partial", "stale"}:
            result_status = cast(ResultStatus, raw_result_status)
        else:
            result_status = "partial" if partial else "ok"
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload=normalized,
            attribution=[str(payload.get("attribution") or "Data from Open-Meteo")],
            fetched_at=self._fetched_at(payload.get("fetched_at")),
            result_status=result_status,
            observation_time=(
                str(payload.get("observation_time"))
                if payload.get("observation_time") is not None
                else None
            ),
            coverage=json_object(payload.get("coverage")) or None,
            spatial_resolution=(
                str(payload.get("spatial_resolution"))
                if payload.get("spatial_resolution")
                else None
            ),
            units={
                str(key): str(value)
                for key, value in json_object(payload.get("units")).items()
                if isinstance(value, str)
            },
            source_url=(
                str(payload.get("source_url"))
                if payload.get("source_url") is not None
                else self._service_source_url(request.capability_id)
            ),
            result_type="features",
            partial=partial,
        )

    # -------------------------------------------------------------------------
    async def _weather_grid(self, request: ProviderRequest) -> ProviderResponse:
        assert request.bbox is not None
        bbox = request.bbox
        region = find_macro_region_entry(str(request.params.get("macro_region") or ""))
        # Building a mask unions many polygons; keep it off the event loop.
        raw_mask_countries = request.params.get("mask_countries")
        mask_countries = (
            tuple(str(code).upper() for code in cast(list[object], raw_mask_countries))
            if isinstance(raw_mask_countries, list)
            else ()
        )
        mask = await asyncio.to_thread(
            land_mask, bbox, region.countries if region is not None else mask_countries
        )
        points, spacing, excluded = await asyncio.to_thread(grid_points, bbox, WEATHER_GRID_POINT_BUDGET, mask)
        if not points:
            raise ProviderUnavailableError("The search area contains no sampled land inside the region.")
        now = datetime.now(UTC)
        window = _forecast_window(request, now)
        past_days = 0 if window is not None else (
            min(14, max(0, math.ceil(max(0.0, (now - request.time).total_seconds() - 60) / 86400))) if request.time else 0
        )
        # A future window ("tomorrow") needs forecast hours, not past ones.
        forecast_days = (
            max(1, min(16, math.ceil((window[1] - now).total_seconds() / 86400) + 1))
            if window is not None
            else 1
        )

        # The grid asks for the exact dated window; only the span the endpoint
        # can serve is requested, so an uncovered remainder shows as partial.
        served = (
            clip_window_to_forecast_range(
                window, now, max_forecast_days=OPENMETEO_WEATHER_MAX_FORECAST_DAYS
            )
            if window is not None
            else None
        )

        async def fetch_grid(grid: list[tuple[float, float]]) -> list[dict[str, Any] | None]:
            if window is None:
                return await self.service.get_weather_grid(grid, past_days)
            if served is None:
                raise ProviderInvalidQueryError(
                    "Open-Meteo serves no hours for the requested window "
                    f"{window[0].isoformat()} to {window[1].isoformat()}."
                )
            return await self.service.get_weather_grid(grid, 0, forecast_days=forecast_days, window=served)

        try:
            samples = await fetch_grid(points)
        except (OpenMeteoServiceError, ValueError) as exc:
            raise _provider_error(exc) from exc
        features = _grid_features(points, samples, past_days, "coarse", window)
        if not features:
            # Land points always have model weather; no usable sample is a
            # failed retrieval, not a legitimately empty area.
            raise ProviderUnavailableError(f"Open-Meteo returned no usable samples for {len(points)} requested points.")
        # Sampling misses local extremes between cells. Re-sample a finer
        # 3x3 neighbourhood around the strongest coarse cells of each metric.
        refined_points = _refinement_points(features, spacing, mask, set(points))
        refined: list[dict[str, Any]] = []
        if refined_points:
            try:
                refined_samples = await fetch_grid(refined_points)
            except OpenMeteoRateLimitError as exc:
                raise _provider_error(exc) from exc
            except (OpenMeteoServiceError, ValueError):
                refined_samples = []
            refined = _grid_features(refined_points, refined_samples, past_days, "refined", window)
        # Every requested coarse and refined point is either a feature or
        # missing: point_count + missing_point_count == all requested points.
        missing = len(points) + len(refined_points) - len(features) - len(refined)
        partial = missing > 0
        features.extend(refined)
        units = {"precipitation_sum_mm": "mm", "temperature_2m_max_c": "\u00b0C", "temperature_2m_current_c": "\u00b0C", "elevation": "m"}
        coverage: dict[str, Any] = {"type": "grid_sample", "bbox": list(bbox), "point_count": len(features),
                    "requested_point_count": len(points), "spacing_deg": spacing,
                    "excluded_outside_region_points": excluded, "mask_source": MASK_SOURCE,
                    "region": region.name if region is not None else None,
                    "mask_countries": list(region.countries if region is not None else mask_countries),
                    "refined_point_count": len(refined), "refinement_requested_point_count": len(refined_points),
                    "refinement_spacing_deg": spacing / 3,
                    "temporal_scope_satisfied": (
                        _window_covered(features, window)
                        if window is not None
                        else request.time is None or now - request.time <= timedelta(days=14)
                    ),
                    "requested_window_utc": (
                        [window[0].isoformat(), window[1].isoformat()] if window is not None else None
                    ),
                    "missing_point_count": missing,
                    "window_start": min((f["window_start"] for f in features), default=None),
                    "window_end": max((f["window_end"] for f in features), default=None),
                    "window_end_utc": max((f["window_end_utc"] for f in features), default=None),
                    "value_kind": "model_estimate", "location_labels": "coordinates"}
        return ProviderResponse(
            capability_id=request.capability_id, provider_id=self.provider_id,
            payload={"features": features, "renderingMode": "circles", "value_kind": "model_estimate", "units": units, "coverage": coverage},
            attribution=["Open-Meteo"], coverage=coverage, units=units,
            result_type="features", result_status="partial" if partial else "ok",
            partial=partial, source_url=self.service.weather_base_url,
            observation_time=coverage["window_end_utc"] or coverage["window_end"],
            spatial_resolution=f"{spacing:.2f} degree grid",
        )

    # -------------------------------------------------------------------------
    def _payload(
        self, payload: dict[str, Any], *, rendering_mode: str
    ) -> dict[str, Any]:
        return {
            "renderingMode": rendering_mode,
            "provider": self.provider_id,
            "kind": payload.get("kind"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "elevation": payload.get("elevation"),
            "timezone": payload.get("timezone"),
            "current": json_object(payload.get("current")),
            "hourlyPreview": json_array(payload.get("hourly_preview")),
            "hourlyForecast": json_array(payload.get("hourly_forecast")),
            "features": self._features(payload, rendering_mode=rendering_mode),
            "resolvedAt": payload.get("resolved_at"),
            "observation_time": payload.get("observation_time"),
            "units": payload.get("units") or {},
            "spatial_resolution": payload.get("spatial_resolution"),
            "coverage": payload.get("coverage"),
            "source_url": payload.get("source_url"),
            "fetched_at": payload.get("fetched_at"),
            "result_status": payload.get("result_status"),
            "partial": bool(payload.get("partial")),
            "window_summary": payload.get("window_summary"),
            "current_in_window": payload.get("current_in_window"),
            "requested_variables": payload.get("requested_variables") or [],
            "request_parameters": payload.get("request_parameters") or {},
        }

    # -------------------------------------------------------------------------
    def _features(
        self, payload: dict[str, Any], *, rendering_mode: str
    ) -> list[dict[str, Any]]:
        if rendering_mode != "clustered-points":
            return []
        if str(payload.get("result_status") or "ok") == "valid_empty":
            return []
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(
            longitude, (int, float)
        ):
            return []
        kind = str(payload.get("kind") or "")
        current = json_object(payload.get("current"))
        if payload.get("current_in_window") is False:
            # Conditions now describe a different instant than the window.
            current = {}
        preview = json_array(payload.get("hourly_preview"))
        first_hour = preview[0] if preview and is_json_object(preview[0]) else {}
        source_url = payload.get("source_url")
        fetched_at = payload.get("fetched_at")
        result_status = payload.get("result_status")
        partial = bool(payload.get("partial"))
        common = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "source_url": source_url,
            "fetched_at": fetched_at,
            "observation_time": payload.get("observation_time"),
            "forecast_time": first_hour.get("time"),
            "timezone": payload.get("timezone"),
            "result_status": result_status,
            "partial": partial,
            "units": json_object(payload.get("units")),
            "request_parameters": json_object(payload.get("request_parameters")),
        }
        if payload.get("window_summary"):
            common["window_summary"] = payload["window_summary"]
        if "elevation" in kind:
            elevation = payload.get("elevation")
            return [
                {
                    "id": f"openmeteo:elevation:{latitude:.4f}:{longitude:.4f}",
                    "name": "Open-Meteo terrain elevation",
                    "category": "terrain",
                    "source": self.provider_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "elevation": elevation,
                    "metadata": {
                        "elevation": elevation,
                        "spatial_resolution": payload.get("spatial_resolution"),
                        **common,
                    },
                }
            ]
        if "air_quality" in kind:
            pollutant_values = {
                key: self._prefer(current.get(key), first_hour.get(key))
                for key in (
                    "pm2_5",
                    "pm10",
                    "nitrogen_dioxide",
                    "ozone",
                    "sulphur_dioxide",
                    "carbon_monoxide",
                )
            }
            return [
                {
                    "id": f"openmeteo:air-quality:{latitude:.4f}:{longitude:.4f}",
                    "name": "Open-Meteo air quality forecast",
                    "category": "air_quality",
                    "source": self.provider_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    **pollutant_values,
                    "metadata": {
                        "pollutantSymbols": {
                            "pm25": pollutant_values["pm2_5"],
                            "pm10": pollutant_values["pm10"],
                            "no2": pollutant_values["nitrogen_dioxide"],
                            "o3": pollutant_values["ozone"],
                            "so2": pollutant_values["sulphur_dioxide"],
                            "co": pollutant_values["carbon_monoxide"],
                        },
                        **common,
                    },
                }
            ]
        weather_values = {
            key: self._prefer(current.get(key), first_hour.get(key))
            for key in (
                "temperature_2m",
                "precipitation",
                "weather_code",
                "relative_humidity_2m",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "precipitation_probability",
            )
        }
        return [
            {
                "id": f"openmeteo:wind:{latitude:.4f}:{longitude:.4f}",
                "name": "Open-Meteo wind forecast",
                "category": "wind",
                "source": self.provider_id,
                "latitude": float(latitude),
                "longitude": float(longitude),
                **weather_values,
                "metadata": {
                    "windArrow": {
                        "speed": weather_values["wind_speed_10m"],
                        "direction": weather_values["wind_direction_10m"],
                    },
                    "pressure": weather_values["surface_pressure"],
                    "humidity": weather_values["relative_humidity_2m"],
                    **common,
                },
            }
        ]

    # -------------------------------------------------------------------------
    def _service_source_url(self, capability_id: str) -> str | None:
        if "elevation" in capability_id:
            return getattr(self.service, "elevation_base_url", None)
        if "air_quality" in capability_id:
            return getattr(self.service, "air_quality_base_url", None)
        return getattr(self.service, "weather_base_url", None)

    # -------------------------------------------------------------------------
    @staticmethod
    def _prefer(primary: object, fallback: object) -> object:
        return primary if primary is not None else fallback

    # -------------------------------------------------------------------------
    @staticmethod
    def _fetched_at(value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
            if parsed is not None:
                return (
                    parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
                )
        return datetime.now(UTC)

###############################################################################
def _requested_end(request: ProviderRequest) -> datetime | None:
    """The explicit window end; a date-only end covers its whole day and an
    end at the last second of a minute is inclusive of that second."""

    raw_end = request.params.get("end_time_iso")
    if not isinstance(raw_end, str) or not raw_end.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
    except ValueError:
        return None
    parsed = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    if len(raw_end.strip()) == 10:
        return parsed + timedelta(days=1)
    parsed = parsed.replace(microsecond=0)
    return parsed + timedelta(seconds=1) if parsed.second == 59 else parsed

###############################################################################
def _requested_window(request: ProviderRequest, now: datetime) -> tuple[datetime, datetime] | None:
    """The explicit UTC window a request addresses, past or future.

    A request without an end that starts now or earlier asks for current
    conditions, not a window.
    """

    start = request.time
    if start is None:
        return None
    end = _requested_end(request)
    if end is None:
        if start <= now + timedelta(minutes=1):
            return None
        end = start + timedelta(days=1)
    return (start, end) if end > start else None

###############################################################################
def _forecast_window(request: ProviderRequest, now: datetime) -> tuple[datetime, datetime] | None:
    """Return the requested UTC window when it lies in the future."""

    window = _requested_window(request, now)
    if window is None:
        return None
    # "Next 24 hours" starts about now; a window ending in the future is a
    # forecast window, while one ending before now stays a past window.
    if window[1] <= now + timedelta(hours=1) or window[0] < now - timedelta(hours=2):
        return None
    return window

###############################################################################
def _provider_error(error: Exception) -> ProviderError:
    """Classify an Open-Meteo failure: 429 capacity, other 4xx unsupported
    (the endpoint explains why), 5xx and transport failures transient."""

    if isinstance(error, OpenMeteoRateLimitError):
        return ProviderRateLimitError(str(error), retry_after_seconds=error.retry_after_seconds)
    if isinstance(error, OpenMeteoRequestError) and error.status_code is not None:
        return provider_error_for_http_status(error.status_code, str(error))
    return ProviderUnavailableError(str(error))

###############################################################################
def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

###############################################################################
def _apply_window(
    payload: dict[str, Any],
    requested: tuple[datetime, datetime],
    served: tuple[datetime, datetime],
    now: datetime,
) -> dict[str, Any]:
    """Restrict a dated point forecast to the requested window and report the
    window actually covered.

    Hours are hour-ending UTC stamps, so an hour belongs to the window when it
    ends after the start and by the end. Coverage is satisfied only when the
    returned hours span the whole requested (not merely the served) window.
    """

    kind = str(payload.get("kind") or "")
    core = ("temperature_2m", "precipitation") if "weather" in kind else None
    rows: list[dict[str, Any]] = []
    stamps: list[datetime] = []
    for raw in json_array(payload.get("hourly_forecast")):
        row = json_object(raw)
        try:
            stamp = datetime.fromisoformat(str(row.get("time"))).replace(tzinfo=UTC)
        except ValueError:
            continue
        if requested[0] < stamp <= requested[1]:
            rows.append(row)
            stamps.append(stamp)
    if not rows:
        raise ProviderUnavailableError("Open-Meteo returned no hours inside the requested window.")
    keys = core or tuple(key for key in rows[0] if key != "time")
    missing_hours = sum(1 for row in rows if not all(_numeric(row.get(key)) for key in keys))
    tolerance = timedelta(hours=1, minutes=1)
    covered = stamps[0] <= requested[0] + tolerance and stamps[-1] >= requested[1] - tolerance
    summary: dict[str, Any] = {"hours": len(rows), "missing_hours": missing_hours}
    variables: dict[str, dict[str, float]] = {}
    for key in rows[0]:
        values = [float(row[key]) for row in rows if key != "time" and _numeric(row.get(key))]
        if values:
            variables[key] = {"min": min(values), "max": max(values)}
    if "precipitation" in variables:
        summary["precipitation_sum_mm"] = round(
            sum(float(row["precipitation"]) for row in rows if _numeric(row.get("precipitation"))), 2
        )
    summary["variables"] = variables
    coverage = dict(json_object(payload.get("coverage")))
    coverage.update({
        "requested_window_utc": [requested[0].isoformat(), requested[1].isoformat()],
        "window_start_utc": stamps[0].isoformat(),
        "window_end_utc": stamps[-1].isoformat(),
        "temporal_scope_satisfied": covered and missing_hours == 0,
        "missing_hours": missing_hours,
    })
    partial = not coverage["temporal_scope_satisfied"]
    payload.update({
        "hourly_forecast": rows,
        "hourly_preview": rows[:6],
        "coverage": coverage,
        "window_summary": summary,
        "current_in_window": requested[0] < now <= requested[1],
        # The forecast addresses the requested window, not the moment the
        # current conditions were sampled; completion checks this instant.
        "observation_time": requested[0].isoformat(),
        "partial": bool(payload.get("partial")) or partial,
    })
    if partial:
        payload["result_status"] = "partial"
    return payload

###############################################################################
def _window_covered(features: list[dict[str, Any]], window: tuple[datetime, datetime]) -> bool:
    """Whether every sampled point spans the requested forecast hours."""

    if not features:
        return False
    tolerance = timedelta(hours=1, minutes=1)
    for feature in features:
        try:
            first = datetime.fromisoformat(str(feature.get("window_start_utc")))
            last = datetime.fromisoformat(str(feature.get("window_end_utc")))
        except ValueError:
            return False
        if first > window[0] + tolerance or last < window[1] - tolerance:
            return False
    return True

###############################################################################
def _grid_features(
    points: list[tuple[float, float]], samples: list[dict[str, Any] | None], past_days: int, stage: str,
    window: tuple[datetime, datetime] | None = None,
) -> list[dict[str, Any]]:
    # Samples join their points by position only; an unaligned list cannot
    # be trusted at any index, so every point of the stage counts as missing.
    if len(samples) != len(points):
        return []
    prefix = "r" if stage == "refined" else ""
    features: list[dict[str, Any]] = []
    for index, (point, sample) in enumerate(zip(points, samples)):
        feature = _grid_feature(f"openmeteo:grid:{prefix}{index}", point, sample, past_days, stage, window) if sample is not None else None
        if feature is not None:
            features.append(feature)
    return features


###############################################################################
def _grid_feature(
    feature_id: str, point: tuple[float, float], payload: dict[str, Any], past_days: int, stage: str,
    window: tuple[datetime, datetime] | None = None,
) -> dict[str, Any] | None:
    current = json_object(payload.get("current"))
    hourly = json_object(payload.get("hourly"))
    current_time = current.get("time")
    times = hourly.get("time", [])
    temperatures = hourly.get("temperature_2m", [])
    precipitation = hourly.get("precipitation", [])
    if not isinstance(current_time, str) or not all(isinstance(series, list) for series in (times, temperatures, precipitation)):
        return None
    # Open-Meteo times share each point's local timezone. Compare local
    # instants only within that point and disclose the per-point window.
    # One malformed stamp makes the whole sample unusable: dropping just
    # that hour would silently understate the window totals.
    try:
        local_end = datetime.fromisoformat(current_time)
        stamps = [datetime.fromisoformat(stamp) if isinstance(stamp, str) else None for stamp in cast(list[object], times)]
    except ValueError:
        return None
    # Aware and naive stamps cannot be ordered against each other.
    if any(stamp is None or (stamp.tzinfo is None) != (local_end.tzinfo is None) for stamp in stamps):
        return None
    offset = payload.get("utc_offset_seconds")
    utc_offset = timedelta(seconds=float(offset)) if isinstance(offset, (int, float)) and not isinstance(offset, bool) else timedelta(0)

    def as_utc(stamp: datetime) -> datetime:
        return stamp.astimezone(UTC) if stamp.tzinfo is not None else (stamp - utc_offset).replace(tzinfo=UTC)

    if window is not None:
        # Forecast hours are hour-ending accumulations: an hour belongs to the
        # window when it ends after the window start and by the window end.
        selected = [
            i for i, stamp in enumerate(stamps)
            if stamp is not None and window[0] < as_utc(stamp) <= window[1]
        ]
    else:
        local_start = local_end - timedelta(days=past_days) if past_days else local_end.replace(hour=0, minute=0, second=0)
        selected = [i for i, stamp in enumerate(stamps) if stamp is not None and local_start <= stamp <= local_end]
    rain = [precipitation[i] if i < len(precipitation) else None for i in selected]
    heat = [temperatures[i] if i < len(temperatures) else None for i in selected]
    def numeric(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not selected or not all(numeric(value) for value in [*rain, *heat, current.get("temperature_2m")]):
        return None
    latitude, longitude = point
    return {
        "id": feature_id, "latitude": latitude, "longitude": longitude,
        "name": f"{latitude:.5f}, {longitude:.5f}", "label_kind": "coordinates",
        "precipitation_sum_mm": sum(float(value) for value in rain if value is not None), "temperature_2m_max_c": max(float(value) for value in heat if value is not None),
        "temperature_2m_current_c": current["temperature_2m"], "elevation": payload.get("elevation"),
        "window_start": times[selected[0]], "window_end": times[selected[-1]], "timezone": payload.get("timezone"),
        "window_start_utc": as_utc(cast(datetime, stamps[selected[0]])).isoformat(),
        "window_end_utc": as_utc(cast(datetime, stamps[selected[-1]])).isoformat(),
        "value_kind": "model_estimate", "sample_stage": stage,
    }


###############################################################################
def _refinement_points(
    features: list[dict[str, Any]], spacing: float, mask: LandMask, existing: set[tuple[float, float]]
) -> list[tuple[float, float]]:
    seeds: list[dict[str, Any]] = []
    for metric in ("precipitation_sum_mm", "temperature_2m_max_c"):
        ranked = sorted(features, key=lambda feature: feature[metric], reverse=True)
        seeds.extend(feature for feature in ranked[:GRID_REFINEMENT_SEEDS_PER_METRIC] if feature not in seeds)
    step = spacing / 3
    points: list[tuple[float, float]] = []
    seen = set(existing)
    for seed in seeds:
        for dy in (-step, 0.0, step):
            for dx in (-step, 0.0, step):
                if dx == 0.0 and dy == 0.0:
                    continue
                latitude, longitude = round(seed["latitude"] + dy, 5), round(seed["longitude"] + dx, 5)
                if (latitude, longitude) in seen or not mask.contains(Point(longitude, latitude)):
                    continue
                seen.add((latitude, longitude))
                points.append((latitude, longitude))
    return points
