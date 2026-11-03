from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError

import pytest

from server.domain.geospatial.providers import ProviderExecutionPolicy, ProviderRequest, ProviderResponse
from server.services.agent.capability_execution import CapabilityExecutionService, ToolExecutionContext
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.geospatial.openmeteo import OpenMeteoService
from server.services.geospatial.overpass import OverpassService, _overpass_http_error  # pyright: ignore[reportPrivateUsage]
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderInvalidQueryError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnsupportedError,
    classify_provider_error,
    provider_error_for_http_status,
)
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider

# --- failure classification --------------------------------------------------


###############################################################################
@pytest.mark.parametrize(
    ("status", "expected_type", "expected_class"),
    [
        (503, ProviderUnavailableError, "transient"),
        (504, ProviderUnavailableError, "transient"),
        (429, ProviderRateLimitError, "capacity"),
        (400, ProviderInvalidQueryError, "unsupported"),
        (401, ProviderAuthError, "credential_missing"),
    ],
)
def test_http_statuses_are_classified(status: int, expected_type: type, expected_class: str) -> None:
    error = provider_error_for_http_status(status, "failed", retry_after_seconds=3.0)
    assert isinstance(error, expected_type)
    assert classify_provider_error(error) == expected_class
    if status == 429:
        assert getattr(error, "retry_after_seconds") == 3.0


###############################################################################
def test_timeouts_are_transient_and_foreign_errors_unclassified() -> None:
    assert classify_provider_error(ProviderTimeoutError("slow")) == "transient"
    assert classify_provider_error(RuntimeError("bug")) is None


###############################################################################
def test_overpass_http_errors_are_classified_with_retry_after() -> None:
    busy = _overpass_http_error(HTTPError("u", 429, "busy", {"Retry-After": "2"}, None))  # type: ignore[arg-type]
    assert classify_provider_error(busy) == "capacity"
    assert getattr(busy, "retry_after_seconds") == 2.0
    assert classify_provider_error(_overpass_http_error(HTTPError("u", 400, "bad", {}, None))) == "unsupported"  # type: ignore[arg-type]
    assert classify_provider_error(_overpass_http_error(HTTPError("u", 504, "gw", {}, None))) == "transient"  # type: ignore[arg-type]


###############################################################################
def test_overpass_resolves_osm_tags_and_amenity_values_and_drops_unsafe_tokens() -> None:
    service = OverpassService(base_url="https://overpass.example/api")
    assert service._category_selectors("education") == OverpassService.CATEGORY_SELECTORS["education"]  # pyright: ignore[reportPrivateUsage]
    assert service._category_selectors("University") == (("amenity", "university"),)  # pyright: ignore[reportPrivateUsage]
    assert service._category_selectors("amenity=college") == (("amenity", "college"),)  # pyright: ignore[reportPrivateUsage]


# --- bounded retry in the provider registry ---------------------------------


###############################################################################
class _ScriptedProvider:

    # -------------------------------------------------------------------------
    def __init__(self, provider_id: str, *outcomes: Exception | ProviderResponse) -> None:
        self.provider_id = provider_id
        self.outcomes = list(outcomes)
        self.calls = 0

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        outcome = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

###############################################################################
def _ok(provider_id: str, capability_id: str = "cap", **overrides: Any) -> ProviderResponse:
    return ProviderResponse(capability_id=capability_id, provider_id=provider_id, payload={"features": []}, **overrides)

###############################################################################
def _registry(provider: _ScriptedProvider, **policy: Any) -> ProviderRegistry:
    return ProviderRegistry(
        providers=[provider],  # type: ignore[list-item]
        execution_policy=ProviderExecutionPolicy(
            max_attempts=2, retry_backoff_base_seconds=0.0, retry_backoff_max_seconds=0.0, **policy
        ),
    )

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProviderUnavailableError("503"), ProviderRateLimitError("429", retry_after_seconds=0.0)])
async def test_transient_and_capacity_failures_retry_exactly_once(error: Exception) -> None:
    provider = _ScriptedProvider("p", error, error, error)
    with pytest.raises(type(error)) as raised:
        await _registry(provider).fetch("p", ProviderRequest(capability_id="cap"))
    assert provider.calls == 2
    assert getattr(raised.value, "attempts") == 2

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [ProviderInvalidQueryError("400"), ProviderUnsupportedError("no live records"), ProviderAuthError("no key")]
)
async def test_unsupported_and_credential_failures_never_retry(error: Exception) -> None:
    provider = _ScriptedProvider("p", error)
    with pytest.raises(type(error)):
        await _registry(provider).fetch("p", ProviderRequest(capability_id="cap"))
    assert provider.calls == 1

###############################################################################
@pytest.mark.asyncio
async def test_cancellation_interrupts_retry_backoff() -> None:
    provider = _ScriptedProvider("p", ProviderRateLimitError("429", retry_after_seconds=1.5), _ok("p"))
    registry = ProviderRegistry(
        providers=[provider],  # type: ignore[list-item]
        execution_policy=ProviderExecutionPolicy(max_attempts=2, retry_backoff_max_seconds=5.0, timeout_seconds=30.0),
    )
    task = asyncio.create_task(registry.fetch("p", ProviderRequest(capability_id="cap")))
    while provider.calls == 0:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
    assert provider.calls == 1

# --- tool result: classification, declared fallback, honest partial ----------


###############################################################################
class _Capabilities:

    # -------------------------------------------------------------------------
    def __init__(self, manifests: dict[str, dict[str, Any]]) -> None:
        self.manifests = manifests

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict[str, Any] | None:
        return self.manifests.get(capability_id)

###############################################################################
class _Runtime:

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return True

###############################################################################
class _Providers:

    # -------------------------------------------------------------------------
    def __init__(self, outcomes: dict[str, Exception | ProviderResponse]) -> None:
        self.outcomes = outcomes
        self.requests: list[tuple[str, str]] = []

    # -------------------------------------------------------------------------
    async def fetch(self, provider_id: str, request: ProviderRequest) -> ProviderResponse:
        self.requests.append((provider_id, request.capability_id))
        outcome = self.outcomes[provider_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

###############################################################################
def _service(providers: _Providers, *, fallback_ids: list[str]) -> CapabilityExecutionService:
    return CapabilityExecutionService(
        capability_registry=_Capabilities({
            "cap": {"id": "cap", "provider": "primary", "executionContract": {"fallback_ids": fallback_ids}},
            "cap_mirror": {"id": "cap_mirror", "provider": "mirror"},
        }),  # type: ignore[arg-type]
        runtime_registry=_Runtime(),  # type: ignore[arg-type]
        provider_registry=providers,  # type: ignore[arg-type]
    )

###############################################################################
async def _run(service: CapabilityExecutionService) -> Any:
    return await service.execute_capability(
        ExecuteCapabilityInput(capability_id="cap"), ToolExecutionContext(conversation_id="c")
    )

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ProviderUnavailableError("503"), "transient"),
        (ProviderTimeoutError("timeout"), "transient"),
        (ProviderRateLimitError("429", retry_after_seconds=1.0), "capacity"),
        (ProviderInvalidQueryError("bad category"), "unsupported"),
        (ProviderUnsupportedError("no live records"), "unsupported"),
        (ProviderAuthError("no key"), "credential_missing"),
    ],
)
async def test_tool_result_names_the_failure_class(error: Exception, expected: str) -> None:
    result = await _run(_service(_Providers({"primary": error}), fallback_ids=[]))
    assert result.status == "failed"
    assert result.data["failure_class"] == expected
    assert f"failure class: {expected}" in result.summary

###############################################################################
@pytest.mark.asyncio
async def test_declared_equivalent_serves_transient_failure() -> None:
    providers = _Providers({"primary": ProviderUnavailableError("502"), "mirror": _ok("mirror", "cap_mirror")})
    result = await _run(_service(providers, fallback_ids=["cap_mirror"]))
    assert result.status in {"success", "valid_empty"}
    assert providers.requests == [("primary", "cap"), ("mirror", "cap_mirror")]
    assert any("declared equivalent 'cap_mirror'" in warning for warning in result.metadata.warnings)

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProviderInvalidQueryError("bad"), ProviderAuthError("no key")])
async def test_no_fallback_for_unsupported_or_credential_failures(error: Exception) -> None:
    providers = _Providers({"primary": error, "mirror": _ok("mirror", "cap_mirror")})
    result = await _run(_service(providers, fallback_ids=["cap_mirror"]))
    assert result.status == "failed"
    assert providers.requests == [("primary", "cap")]

###############################################################################
@pytest.mark.asyncio
async def test_undeclared_or_unknown_equivalents_are_not_invented() -> None:
    providers = _Providers({"primary": ProviderUnavailableError("502"), "mirror": _ok("mirror", "cap_mirror")})
    for declared in ([], ["not_in_catalog"]):
        providers.requests.clear()
        result = await _run(_service(providers, fallback_ids=declared))
        assert result.status == "failed"
        assert providers.requests == [("primary", "cap")]
    assert result.data["fallbacks_tried"] == []

###############################################################################
@pytest.mark.asyncio
async def test_window_not_fully_covered_is_never_complete() -> None:
    coverage = {
        "type": "point",
        "requested_window_utc": ["2026-11-04T00:00:00+00:00", "2026-11-05T00:00:00+00:00"],
        "temporal_scope_satisfied": False,
    }
    result = await _run(_service(_Providers({"primary": _ok("primary", coverage=coverage)}), fallback_ids=[]))
    assert result.status == "partial"
    assert result.metadata.coverage["temporal_scope_satisfied"] is False

# --- Open-Meteo requests the exact window ------------------------------------


###############################################################################
def _hourly_service(captured: list[dict[str, Any]], *, hours: int = 24, skip_first: int = 0) -> OpenMeteoService:
    service = OpenMeteoService(weather_base_url="https://weather.example/forecast")

    # -------------------------------------------------------------------------
    async def get_json(**kwargs: Any) -> dict[str, Any]:
        params = kwargs["params"]
        captured.append(params)
        first = datetime.combine(date.fromisoformat(params["start_date"]), datetime.min.time())
        times = [first + timedelta(hours=1 + skip_first + index) for index in range(hours)]
        values = {name: [1.0] * len(times) for name in OpenMeteoService.WEATHER_VARIABLES}
        return {
            "timezone": "UTC",
            "current": {"time": times[0].isoformat(timespec="minutes"), **{n: 1.0 for n in OpenMeteoService.WEATHER_CURRENT_VARIABLES}},
            "hourly": {"time": [stamp.isoformat(timespec="minutes") for stamp in times], **values},
        }

    service._get_json = get_json  # type: ignore[method-assign]
    return service

###############################################################################
def _tomorrow() -> tuple[datetime, datetime]:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return start, start + timedelta(hours=23, minutes=59, seconds=59)

###############################################################################
def _request(start: datetime, end: datetime) -> ProviderRequest:
    return ProviderRequest(
        capability_id="openmeteo_weather_forecast",
        time=start,
        params={"latitude": 45.46, "longitude": 9.19, "end_time_iso": end.isoformat()},
    )

###############################################################################
@pytest.mark.asyncio
async def test_openmeteo_requests_the_exact_dates_of_tomorrow() -> None:
    captured: list[dict[str, Any]] = []
    start, end = _tomorrow()
    response = await OpenMeteoProvider(service=_hourly_service(captured)).fetch(_request(start, end))

    # Hours are hour-ending, so the window's last hour is stamped on the next date.
    assert captured[0]["start_date"] == start.date().isoformat()
    assert captured[0]["end_date"] == (start + timedelta(days=1)).date().isoformat()
    assert captured[0]["timezone"] == "UTC"
    assert "forecast_days" not in captured[0]
    assert (response.coverage or {})["temporal_scope_satisfied"] is True
    assert (response.coverage or {})["window_start_utc"] == (start + timedelta(hours=1)).isoformat()
    assert response.payload["window_summary"]["precipitation_sum_mm"] == 24.0
    assert response.observation_time == start.isoformat()
    assert not response.partial

###############################################################################
@pytest.mark.asyncio
async def test_openmeteo_window_coverage_is_false_when_hours_are_missing() -> None:
    start, end = _tomorrow()
    response = await OpenMeteoProvider(service=_hourly_service([], hours=12)).fetch(_request(start, end))

    assert (response.coverage or {})["temporal_scope_satisfied"] is False
    assert (response.coverage or {})["requested_window_utc"] == [start.isoformat(), (end + timedelta(seconds=1)).isoformat()]
    assert response.partial
    assert response.result_status == "partial"

###############################################################################
@pytest.mark.asyncio
async def test_openmeteo_other_window_than_requested_is_not_served_as_data() -> None:
    start, end = _tomorrow()
    other = _hourly_service([], hours=24, skip_first=24 * 3)
    with pytest.raises(ProviderUnavailableError):
        await OpenMeteoProvider(service=other).fetch(_request(start, end))

###############################################################################
@pytest.mark.asyncio
async def test_openmeteo_window_beyond_forecast_range_is_unsupported() -> None:
    start = datetime.now(UTC) + timedelta(days=60)
    with pytest.raises(ProviderInvalidQueryError):
        await OpenMeteoProvider(service=_hourly_service([])).fetch(_request(start, start + timedelta(days=1)))

###############################################################################
@pytest.mark.asyncio
async def test_openmeteo_air_quality_uses_the_same_window_parameters() -> None:
    captured: list[dict[str, Any]] = []
    service = OpenMeteoService(air_quality_base_url="https://air.example/forecast")
    start, end = _tomorrow()

    # -------------------------------------------------------------------------
    async def get_json(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs["params"])
        first = datetime.combine(start.date(), datetime.min.time())
        times = [(first + timedelta(hours=1 + index)).isoformat(timespec="minutes") for index in range(24)]
        return {"timezone": "UTC", "hourly": {"time": times, **{n: [2.0] * 24 for n in OpenMeteoService.AIR_QUALITY_VARIABLES}}}

    service._get_json = get_json  # type: ignore[method-assign]
    request = ProviderRequest(
        capability_id="openmeteo_air_quality_forecast",
        time=start,
        params={"latitude": 45.46, "longitude": 9.19, "end_time_iso": end.isoformat()},
    )
    response = await OpenMeteoProvider(service=service).fetch(request)

    assert captured[0]["start_date"] == start.date().isoformat()
    assert captured[0]["timezone"] == "UTC"
    assert (response.coverage or {})["temporal_scope_satisfied"] is True
