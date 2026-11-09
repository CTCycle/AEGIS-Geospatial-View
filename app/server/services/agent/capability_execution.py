"""Canonical provider-backed capability execution for native agent tools."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from collections.abc import Sequence
from typing import Any, Literal, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from shapely.geometry import Point, box, shape
from shapely.errors import GEOSException

from server.common.identifiers import normalize_target_key
from server.common.logging_handlers import log_unexpected_failure
from server.common.typing import (
    is_json_array,
    is_json_object,
    json_array,
    json_object,
    with_nested_scalars,
)
from server.domain.agent.capability_route import ConversationTask
from server.domain.agent.evidence import AgentEvidenceSummary, EvidenceKind, EvidenceStatus
from server.domain.agent.task_ledger import freshness_seconds
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.geospatial.providers import ProviderRequest, ProviderResponse
from server.repositories.agent_evidence import (
    AgentEvidenceRepository,
    create_evidence_async,
)
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.land_mask import country_at
from server.services.geospatial.provider_registry import (
    ProviderNotRegisteredError,
    ProviderRegistry,
)
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderCircuitOpenError,
    ProviderError,
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUnsupportedError,
    classify_provider_error,
)
from server.services.geospatial.runtime_registry import RuntimeRegistry

LOGGER = logging.getLogger(__name__)

# Hourly rows kept in the model-facing summary of a dated window.
WINDOW_HOURS_LIMIT = 72

###############################################################################
class EvidenceStore(Protocol):

    # -------------------------------------------------------------------------
    def create(
        self,
        *,
        conversation_id: str,
        run_id: str | None,
        kind: EvidenceKind,
        media_type: str,
        status: EvidenceStatus,
        payload: Any,
        summary: dict[str, Any],
        provenance: dict[str, Any],
        parent_evidence_ids: list[str] | None = None,
    ) -> Any: ...

    # -------------------------------------------------------------------------
    def get_summary(
        self, evidence_id: str, *, conversation_id: str | None = None
    ) -> AgentEvidenceSummary | None: ...

###############################################################################
@dataclass(frozen=True)
class ToolExecutionContext:
    """Bounded context needed to execute and persist one capability call."""

    conversation_id: str
    run_id: str | None = None
    call_id: str = field(default_factory=lambda: f"call_{uuid4().hex}")

###############################################################################
class CapabilityExecutionService:
    """Execute one manifest capability and normalize it to ``ToolResult``.

    Provider retries, rate limiting, and circuit breaking remain owned by
    ``ProviderRegistry``.  This service performs capability/runtime checks,
    builds the provider-neutral request, serves a transient or capacity
    failure from the capability's declared equivalent (``fallback_ids``),
    persists complete evidence, and returns a bounded model-facing summary
    that names the failure class.
    """

    TOOL_NAME = "execute_geospatial_capability"

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        runtime_registry: RuntimeRegistry,
        provider_registry: ProviderRegistry,
        evidence_repository: EvidenceStore | AgentEvidenceRepository | None = None,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry
        self.provider_registry = provider_registry
        self.evidence_repository = evidence_repository

    # -------------------------------------------------------------------------
    async def execute_capability(
        self,
        request: ExecuteCapabilityInput,
        context: ToolExecutionContext,
        *,
        location: ResolvedLocation | None = None,
    ) -> ToolResult:
        started = time.perf_counter()
        capability_id = request.capability_id

        try:
            manifest = self.capability_registry.get_capability(capability_id)
        except Exception as exc:
            log_unexpected_failure(
                LOGGER, exc, stage="capability_lookup", run_id=context.run_id,
                capability=capability_id, call_id=context.call_id,
            )
            return self._failure(
                context=context,
                capability_id=capability_id,
                started=started,
                error_type="internal_error",
                code="capability_lookup_failed",
                message="The capability could not be inspected.",
                recovery="terminal",
            )
        if manifest is None:
            return self._failure(
                context=context,
                capability_id=capability_id,
                started=started,
                error_type="unknown_tool",
                code="unknown_capability",
                message="The requested capability is not in the validated catalog.",
                recovery="choose_alternate_tool",
            )

        try:
            if not self.runtime_registry.is_enabled(capability_id):
                return self._failure(
                    context=context,
                    capability_id=capability_id,
                    started=started,
                    error_type="policy_rejection",
                    code="capability_disabled",
                    message="The requested capability is disabled.",
                    recovery="choose_alternate_tool",
                )
            if not self.runtime_registry.access_available(capability_id):
                return self._failure(
                    context=context,
                    capability_id=capability_id,
                    started=started,
                    error_type="provider_unavailable",
                    code="capability_access_unavailable",
                    message="The requested capability is not currently available.",
                    recovery="choose_alternate_tool",
                )
        except Exception as exc:
            log_unexpected_failure(
                LOGGER, exc, stage="runtime_eligibility", run_id=context.run_id,
                capability=capability_id, call_id=context.call_id,
            )
            return self._failure(
                context=context,
                capability_id=capability_id,
                started=started,
                error_type="internal_error",
                code="runtime_eligibility_failed",
                message="Capability availability could not be verified.",
                recovery="terminal",
            )

        provider_id = _provider_id(manifest)
        if not provider_id:
            return self._failure(
                context=context,
                capability_id=capability_id,
                started=started,
                error_type="semantic_validation",
                code="provider_not_declared",
                message="The capability does not declare an executable provider.",
                recovery="choose_alternate_tool",
            )

        request_time, time_error = _parse_request_time(request.start_time_iso)
        if time_error is not None:
            return self._failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error_type="semantic_validation",
                code="invalid_start_time",
                message=time_error,
                recovery="correct_arguments",
                retryable=True,
            )

        provider_params = _provider_params(request, location=location, manifest=manifest)
        manifest_metadata = manifest.get("metadata")
        if is_json_object(manifest_metadata):
            provider_params.setdefault("metadata", dict(manifest_metadata))
        provider_request = ProviderRequest(
            capability_id=capability_id,
            bbox=_bbox(request.bbox),
            time=request_time,
            params=provider_params,
        )
        fallbacks_tried: list[str] = []
        try:
            response = await self.provider_registry.fetch(
                provider_id,
                provider_request,
            )
        except Exception as exc:
            fallback = await self._fetch_declared_fallback(
                manifest, provider_id, provider_request, exc, fallbacks_tried
            )
            if fallback is None:
                return self._provider_failure(
                    context=context,
                    capability_id=capability_id,
                    provider_id=provider_id,
                    started=started,
                    error=exc,
                    fallbacks_tried=fallbacks_tried,
                )
            response = fallback

        response = _with_honest_partial(response)
        status = _tool_status(response)
        summary = _response_summary(response, request=request, location=location)
        unmet_attributes = _unmet_requested_attributes(request, response, summary)
        if unmet_attributes:
            # A requested variable the source does not carry is an unmet part
            # of the request, never a silent omission.
            summary["unmet_requested_attributes"] = unmet_attributes
            summary["warnings"] = [
                *summary.get("warnings", []),
                f"This source does not provide the requested {', '.join(unmet_attributes)}.",
            ]
        coverage = dict(response.coverage or {})
        if request.arguments.get("sampling") == "area" and "sampling" not in provider_params:
            coverage["area_sampling"] = (
                "bbox_query" if request.bbox is not None and coverage.get("bbox") == list(request.bbox)
                else "single_point_center"
            )
        if coverage.get("type") == "grid_sample" and request.bbox is not None:
            coverage["spatial_scope_satisfied"] = True
        if str(coverage.get("type") or "").strip().casefold() == "circle":
            # Provider-bounded radius results (Overpass ``around``) declare a
            # circle coverage (center + radius_m). The provider already bounded
            # the feature set to that circle, which is the authoritative scope;
            # the geocoder bbox is too narrow for POI/landmark "around <place>"
            # requests and must not reject the render.
            coverage["spatial_scope_satisfied"] = True
        elif response.result_type == "raster":
            # Raster/descriptor results serve the requested bounds directly
            # instead of returning intersection-checkable geometries. A
            # successful renderable result over a bounded or resolved-location
            # request satisfies the spatial scope contract (mirrors
            # RainViewer's provider coverage declaration).
            coverage["spatial_scope_satisfied"] = (
                request.bbox is not None or request.location_ref is not None
            )
        elif request.bbox is not None:
            features = response.payload.get("features")
            if is_json_array(features) and features:
                area = box(request.bbox[0], request.bbox[1], request.bbox[2], request.bbox[3])
                try:
                    satisfied = True
                    for feature in features:
                        geometry = _feature_spatial_geometry(feature)
                        if (
                            not is_json_object(feature)
                            or geometry is None
                            or geometry.is_empty
                            or not geometry.is_valid
                            or not area.intersects(geometry)
                        ):
                            satisfied = False
                            break
                    coverage["spatial_scope_satisfied"] = satisfied
                except (ValueError, TypeError, KeyError, GEOSException):
                    coverage["spatial_scope_satisfied"] = False
            elif response.result_status == "valid_empty":
                # A bounded empty result still applied the requested extent.
                coverage["spatial_scope_satisfied"] = True
        elif request.location_ref is not None:
            # A resolved-location (point/radius) vector request: the provider
            # returns features already bounded to the resolved location scope,
            # mirroring the raster spatial-scope contract. Bbox requests take
            # the intersection-check branch above.
            coverage["spatial_scope_satisfied"] = True
        if (
            request.start_time_iso is None and request.end_time_iso is None
        ):
            # Current/recent/none temporal requests without an explicit dated
            # range are satisfied by the provider feed as-is (mirrors
            # RainViewer's provider coverage declaration). Explicit dated
            # ranges are verified by the observation-time boundary in the
            # completion assessment instead.
            # A provider that declared its own window coverage keeps its verdict.
            coverage.setdefault("temporal_scope_satisfied", True)
        if response.result_type == "raster" and response.result_status != "valid_empty":
            frame_warning = _single_frame_scope_warning(request, coverage)
            if frame_warning:
                # One frame cannot answer a multi-day window or an aggregation;
                # it still renders, with the limitation disclosed.
                summary["warnings"] = [*summary.get("warnings", []), frame_warning]
        if response.result_status == "valid_empty":
            # A completed empty query is a legitimate data outcome; it must not
            # be conflated with a failed/partial fetch. Mark the query as
            # complete so the completion assessment accepts the honest
            # no-results boundary (mirrors the valid-empty evidence contract).
            coverage["query_complete"] = True
        summary["coverage"] = coverage
        summary["value_kind"] = response.payload.get("value_kind") or coverage.get("value_kind")
        try:
            evidence_ref = await self._persist_evidence(
                context=context,
                request=request,
                response=response,
                summary=summary,
            )
        except Exception as exc:
            return self._provider_failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error=exc,
            )
        evidence_refs = [evidence_ref] if evidence_ref else []
        result_size = _json_size(response.payload)
        return ToolResult(
            call_id=context.call_id,
            tool_name=self.TOOL_NAME,
            status=status,
            summary=_summary_text(response, summary),
            data=summary,
            evidence_refs=evidence_refs,
            metadata=ToolExecutionMetadata(
                capability_id=capability_id,
                provider_id=provider_id,
                duration_ms=_duration_ms(started),
                result_size_bytes=result_size,
                evidence_refs=evidence_refs,
                result_type=response.result_type,
                result_status=response.result_status,
                stale=response.stale,
                fetched_at=response.fetched_at.isoformat(),
                observation_time=response.observation_time,
                spatial_resolution=response.spatial_resolution,
                units=dict(response.units),
                coverage=coverage or None,
                warnings=[str(item)[:300] for item in response.warnings[:8]],
                source_url=response.source_url[:500] if response.source_url else None,
            ),
        )

    # -------------------------------------------------------------------------
    async def reuse_evidence(
        self,
        request: ExecuteCapabilityInput,
        context: ToolExecutionContext,
        tasks: Sequence[ConversationTask],
        *,
        now: datetime,
    ) -> ToolResult | None:
        """Answer a bound execute call from an earlier turn's evidence.

        ``tasks`` are the ledger entries the run's goal may reuse.  A stored
        record qualifies only when it was produced by this exact request
        (time bounds may drift within the evidence lifetime) and is still
        fresh; a changed window, filter or place makes a provider call.
        """

        repository = self.evidence_repository
        if repository is None:
            return None
        started = time.perf_counter()
        ttl = freshness_seconds(self.capability_registry.get_capability(request.capability_id))
        key = request_key(request)
        for task in reversed(tasks):
            if task.kind != "data" or task.capability_id != request.capability_id:
                continue
            for evidence_ref in reversed(task.evidence_refs):
                record = await asyncio.to_thread(
                    repository.get_summary, evidence_ref, conversation_id=context.conversation_id
                )
                if record is None or record.status in {"failed", "superseded"}:
                    continue
                fetched_at = record.provenance.get("fetched_at")
                stored = json_object(record.provenance.get("request"))
                if (
                    not isinstance(fetched_at, str)
                    or not stored
                    or not _same_request(stored, key, tolerance_seconds=ttl)
                    or now - _aware_instant(fetched_at) > timedelta(seconds=ttl)
                ):
                    continue
                return _reused_result(
                    record, request=request, context=context, started=started, fetched_at=fetched_at
                )
        return None

    # -------------------------------------------------------------------------
    async def _persist_evidence(
        self,
        *,
        context: ToolExecutionContext,
        request: ExecuteCapabilityInput,
        response: ProviderResponse,
        summary: dict[str, Any],
    ) -> str | None:
        repository = self.evidence_repository
        if repository is None:
            return None
        try:
            record = await create_evidence_async(
                repository,
                conversation_id=context.conversation_id,
                run_id=context.run_id,
                kind=_evidence_kind(response.result_type),
                media_type="application/json",
                status=_evidence_status(response),
                payload=response.payload,
                summary=summary,
                provenance={
                    "capability_id": request.capability_id,
                    "provider_id": response.provider_id,
                    "fetched_at": response.fetched_at.isoformat(),
                    "result_type": response.result_type,
                    "observation_time": response.observation_time,
                    "parent_evidence_refs": list(request.evidence_refs),
                    # The bound request this evidence answers; the reuse gate
                    # matches later calls against it.
                    "request": request_key(request),
                },
                parent_evidence_ids=list(request.evidence_refs),
            )
            return str(getattr(record, "evidence_id", "")).strip() or None
        except Exception as exc:
            raise ProviderMalformedPayloadError(
                "Normalized provider evidence could not be persisted."
            ) from exc

    # -------------------------------------------------------------------------
    async def _fetch_declared_fallback(
        self,
        manifest: dict[str, Any],
        provider_id: str,
        request: ProviderRequest,
        error: Exception,
        tried: list[str],
    ) -> ProviderResponse | None:
        """Serve a retried-out transient or capacity failure from a capability
        the catalog declares equivalent (``executionContract.fallback_ids``).

        Nothing is inferred: undeclared, disabled, or unavailable equivalents
        are skipped, and an unsupported or credential failure is never
        re-asked elsewhere.
        """

        if classify_provider_error(error) not in {"transient", "capacity"}:
            return None
        declared = json_object(manifest.get("executionContract")).get("fallback_ids", [])
        for raw_id in declared if is_json_array(declared) else []:
            fallback_id = str(raw_id).strip()
            try:
                equivalent = self.capability_registry.get_capability(fallback_id)
                fallback_provider = _provider_id(equivalent) if equivalent else ""
                if (
                    equivalent is None
                    or not fallback_provider
                    or (fallback_id, fallback_provider) == (request.capability_id, provider_id)
                    or not self.runtime_registry.is_enabled(fallback_id)
                    or not self.runtime_registry.access_available(fallback_id)
                ):
                    continue
                params = dict(request.params)
                metadata = equivalent.get("metadata")
                if is_json_object(metadata):
                    params["metadata"] = dict(metadata)
                tried.append(fallback_id)
                response = await self.provider_registry.fetch(
                    fallback_provider,
                    replace(request, capability_id=fallback_id, params=params),
                )
            except Exception as exc:
                LOGGER.info(
                    "capability fallback failed capability=%s fallback=%s error=%s",
                    request.capability_id, fallback_id, type(exc).__name__,
                )
                continue
            note = (
                f"Served by declared equivalent '{fallback_id}' after "
                f"'{request.capability_id}' failed ({classify_provider_error(error)})."
            )
            return replace(response, warnings=[*response.warnings, note])
        return None

    # -------------------------------------------------------------------------
    def _provider_failure(
        self,
        *,
        context: ToolExecutionContext,
        capability_id: str,
        provider_id: str,
        started: float,
        error: Exception,
        fallbacks_tried: list[str] | None = None,
    ) -> ToolResult:
        error_type, code, message, recovery, retryable, timeout_origin = _failure_shape(error)
        failure_class = classify_provider_error(error)
        attempts = error.attempts if isinstance(error, ProviderError) else 1
        data: dict[str, Any] | None = None
        if failure_class is not None:
            data = {
                "failure_class": failure_class,
                "attempts": attempts,
                "fallbacks_tried": list(fallbacks_tried or []),
            }
            message = f"{message} (failure class: {failure_class}; {attempts} attempt(s))"
            if isinstance(error, ProviderInvalidQueryError) and str(error).strip():
                # Query rejections are deterministic and carry the provider's
                # own explanation, which is what the next call must change.
                message = f"{message}: {str(error).strip()[:240]}"
        return self._failure(
            context=context,
            capability_id=capability_id,
            provider_id=provider_id,
            started=started,
            error_type=error_type,
            code=code,
            message=message,
            recovery=recovery,
            retryable=retryable,
            timeout_origin=timeout_origin,
            data=data,
        )

    # -------------------------------------------------------------------------
    def _failure(
        self,
        *,
        context: ToolExecutionContext,
        capability_id: str,
        started: float,
        error_type: Any,
        code: str,
        message: str,
        recovery: Any,
        provider_id: str | None = None,
        retryable: bool = False,
        timeout_origin: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> ToolResult:
        error = ToolExecutionError(
            error_type=error_type,
            code=code,
            message=message,
            retryable=retryable,
            recovery=recovery,
            timeout_origin=timeout_origin,
        )
        return ToolResult(
            call_id=context.call_id,
            tool_name=self.TOOL_NAME,
            status="failed",
            summary=message,
            data=data,
            error=error,
            metadata=ToolExecutionMetadata(
                capability_id=capability_id,
                provider_id=provider_id,
                duration_ms=_duration_ms(started),
            ),
        )

###############################################################################
_REQUEST_TIME_KEYS = ("start_time_iso", "end_time_iso")

###############################################################################
def request_key(request: ExecuteCapabilityInput) -> dict[str, Any]:
    """Canonical identity of a bound execute request (what the provider is asked)."""

    return {
        "capability_id": request.capability_id,
        "operation": request.operation,
        "temporal_mode": request.temporal_mode,
        "location_ref": normalize_target_key(request.location_ref) if request.location_ref else None,
        "evidence_refs": sorted(request.evidence_refs),
        "radius_m": request.radius_m,
        "bbox": [round(value, 6) for value in request.bbox] if request.bbox is not None else None,
        "start_time_iso": request.start_time_iso,
        "end_time_iso": request.end_time_iso,
        "filters": json.loads(json.dumps(request.filters, sort_keys=True, default=str)),
        "arguments": json.loads(json.dumps(request.arguments, sort_keys=True, default=str)),
    }

###############################################################################
def _same_request(stored: dict[str, Any], key: dict[str, Any], *, tolerance_seconds: int) -> bool:
    """Equal request identity; time bounds may drift within the evidence lifetime."""

    if {name: value for name, value in stored.items() if name not in _REQUEST_TIME_KEYS} != {
        name: value for name, value in key.items() if name not in _REQUEST_TIME_KEYS
    }:
        return False
    for name in _REQUEST_TIME_KEYS:
        left, right = stored.get(name), key.get(name)
        if left is None and right is None:
            continue
        if not isinstance(left, str) or not isinstance(right, str):
            return False
        try:
            drift = abs(_aware_instant(left) - _aware_instant(right))
        except ValueError:
            return False
        if drift > timedelta(seconds=tolerance_seconds):
            return False
    return True

###############################################################################
def _aware_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

###############################################################################
def _reused_result(
    record: AgentEvidenceSummary,
    *,
    request: ExecuteCapabilityInput,
    context: ToolExecutionContext,
    started: float,
    fetched_at: str,
) -> ToolResult:
    summary = dict(record.summary)
    evidence_refs = [record.evidence_id]
    units = json_object(summary.get("units"))
    coverage = json_object(summary.get("coverage"))
    status: Literal["success", "valid_empty", "partial"] = (
        "valid_empty"
        if record.status == "valid_empty"
        else "partial"
        if record.status == "partial"
        else "success"
    )
    return ToolResult(
        call_id=context.call_id,
        tool_name=CapabilityExecutionService.TOOL_NAME,
        status=status,
        summary=(
            f"Reused evidence {record.evidence_id} from an earlier turn (fetched {fetched_at}) "
            "for this identical request; no provider request was made."
        ),
        data={**summary, "reused_evidence_ref": record.evidence_id},
        evidence_refs=evidence_refs,
        metadata=ToolExecutionMetadata(
            capability_id=request.capability_id,
            provider_id=str(record.provenance.get("provider_id") or "") or None,
            duration_ms=_duration_ms(started),
            evidence_refs=evidence_refs,
            result_type=str(record.provenance.get("result_type") or "") or None,
            result_status=str(summary.get("result_status") or "") or None,
            stale=bool(summary.get("stale")),
            fetched_at=fetched_at,
            observation_time=str(record.provenance.get("observation_time") or "") or None,
            units={str(name): str(value) for name, value in units.items()},
            coverage=coverage or None,
            warnings=[str(item)[:300] for item in json_array(summary.get("warnings"))[:8]],
            source_url=str(summary.get("source_url") or "")[:500] or None,
        ),
    )

###############################################################################
def _failure_shape(error: Exception) -> tuple[Any, str, str, Any, bool, str | None]:
    """(error_type, code, message, recovery, retryable, timeout_origin)."""

    if isinstance(error, ProviderInvalidQueryError):
        return (
            "semantic_validation", "provider_invalid_query",
            "The provider rejected the validated query.", "correct_arguments", True, None,
        )
    if isinstance(error, ProviderUnsupportedError):
        return (
            "provider_unavailable", "provider_unsupported",
            "The provider cannot serve this capability at query time.",
            "choose_alternate_tool", False, None,
        )
    if isinstance(error, ProviderAuthError):
        return (
            "authentication", "provider_authentication",
            "Provider authentication is unavailable.", "choose_alternate_tool", False, None,
        )
    if isinstance(error, ProviderRateLimitError):
        return (
            "rate_limit", "provider_rate_limit",
            "The provider rate limit was reached.", "retry_transport", False, None,
        )
    if isinstance(error, ProviderTimeoutError):
        return (
            "timeout", "provider_timeout",
            "The provider did not respond within its execution deadline.",
            "replan", False, "provider_transport",
        )
    if isinstance(error, ProviderMalformedPayloadError):
        return (
            "provider_malformed_response", "provider_malformed_response",
            "The provider response could not be normalized or stored.",
            "choose_alternate_tool", False, None,
        )
    if isinstance(
        error,
        (ProviderCircuitOpenError, ProviderUnavailableError, ProviderNotRegisteredError, ProviderError),
    ):
        return (
            "provider_unavailable", "provider_unavailable",
            "The provider is temporarily unavailable.", "choose_alternate_tool", False, None,
        )
    return (
        "internal_error", "capability_execution_failed",
        "The capability failed during execution.", "terminal", False, None,
    )

###############################################################################
def _with_honest_partial(response: ProviderResponse) -> ProviderResponse:
    """A dated request the returned hours do not fully cover is partial.

    Providers declare the window they actually covered next to the requested
    one; a result that misses part of it must never be presented as complete.
    """

    coverage = response.coverage or {}
    if (
        coverage.get("requested_window_utc")
        and coverage.get("temporal_scope_satisfied") is False
        and response.result_status == "ok"
    ):
        return replace(
            response,
            result_status="partial",
            partial=True,
            warnings=[
                *response.warnings,
                "The returned data does not cover the whole requested time window.",
            ],
        )
    return response

###############################################################################
def _provider_id(manifest: dict[str, Any]) -> str:
    return str(manifest.get("provider") or manifest.get("provider_id") or "").strip()

###############################################################################
def _bbox(value: list[float] | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    return tuple(float(item) for item in value)  # type: ignore[return-value]

###############################################################################
def _feature_spatial_geometry(value: Any) -> Any | None:
    """Return the shapely geometry for a GeoJSON or normalized point feature.

    Several adapters (USGS, Open-Meteo, NOAA CO-OPS, Overpass) return
    normalized features with top-level ``latitude``/``longitude`` instead of a
    GeoJSON ``geometry`` object. The spatial-scope intersection check must
    accept both shapes, otherwise bounded requests incorrectly report
    ``spatial_scope_satisfied=false``.
    """
    if not is_json_object(value):
        return None
    geometry = value.get("geometry")
    if is_json_object(geometry):
        try:
            return shape(geometry)
        except (ValueError, TypeError, KeyError, GEOSException):
            return None
    latitude = value.get("latitude")
    longitude = value.get("longitude")
    if isinstance(latitude, int | float) and isinstance(longitude, int | float):
        return Point(float(longitude), float(latitude))
    return None

###############################################################################
def _provider_params(
    request: ExecuteCapabilityInput,
    *,
    location: ResolvedLocation | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = dict(request.arguments)
    scopes = json_object((manifest or {}).get("executionContract")).get("supported_scope_kinds", [])
    if "grid_sample" not in scopes:
        params.pop("sampling", None)
    if location is not None:
        # Provider adapters are deliberately location-agnostic at the model
        # boundary.  Inject the server-resolved point after tool validation so
        # a location_ref is useful to every provider without trusting model
        # supplied coordinates.
        params["latitude"] = location.latitude
        params["longitude"] = location.longitude
        if location.wikidata_id:
            params["wikidata_id"] = location.wikidata_id
        if location.source == "aegis_macro_regions":
            params["macro_region"] = location.label
        elif location.location_type == "country":
            # A country-wide grid must not sample neighbouring land inside the
            # country's bounding box.
            country_code = country_at(location.longitude, location.latitude)
            if country_code:
                params["mask_countries"] = [country_code]
    if request.operation is not None:
        params.setdefault("operation", request.operation)
    if request.location_ref is not None:
        params.setdefault("location_ref", request.location_ref)
    if request.evidence_refs:
        params.setdefault("evidence_refs", list(request.evidence_refs))
    if request.radius_m is not None:
        params.setdefault("radius_m", request.radius_m)
    if request.temporal_mode is not None:
        params.setdefault("temporal_mode", request.temporal_mode)
    if request.filters:
        params["filters"] = dict(request.filters)
    if request.end_time_iso is not None:
        params.setdefault("end_time_iso", request.end_time_iso)
    return params

###############################################################################
def _parse_request_time(value: str | None) -> tuple[datetime | None, str | None]:
    if not value:
        return None, None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "The start time must be a valid ISO-8601 timestamp."
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed, None

###############################################################################
def _tool_status(response: ProviderResponse) -> Any:
    if response.result_status == "valid_empty":
        return "valid_empty"
    if response.result_status in {"partial", "stale"} or response.partial:
        return "partial"
    return "success"

###############################################################################
def _evidence_status(response: ProviderResponse) -> EvidenceStatus:
    if response.result_status == "valid_empty":
        return "valid_empty"
    if response.result_status in {"partial", "stale"} or response.partial:
        return "partial"
    return "available"

###############################################################################
def _evidence_kind(result_type: str) -> EvidenceKind:
    if result_type == "features":
        return "vector"
    if result_type == "raster":
        return "raster_descriptor"
    return "capability_result"

###############################################################################
def _requested_attributes(request: ExecuteCapabilityInput | None) -> list[str]:
    values = request.arguments.get("requested_attributes") if request is not None else None
    if not is_json_array(values):
        return []
    return list(dict.fromkeys(
        name for item in values
        if (name := re.sub(r"[^a-z0-9]+", "_", str(item).strip().casefold()).strip("_"))
    ))

###############################################################################
def _unmet_requested_attributes(
    request: ExecuteCapabilityInput, response: ProviderResponse, summary: dict[str, Any]
) -> list[str]:
    """Requested variables absent from a result whose fields are known.

    Only weather/air-quality series and sampled grids are checked: their
    field set is declared by the provider adapter, so absence is a verdict.
    """

    requested = _requested_attributes(request)
    if not requested:
        return []
    features = response.payload.get("features")
    if str((response.coverage or {}).get("type") or "") == "grid_sample" and is_json_array(features):
        rows: list[Any] = features[:200]
    elif response.payload.get("kind") in {"weather_forecast", "air_quality_forecast"}:
        rows = json_array(summary.get("hourly_forecast"))
    else:
        return []
    keys = {str(key).replace("_", "") for row in rows if is_json_object(row) for key in row}
    if not keys:
        return []
    return [
        name for name in requested
        if not any(key.startswith(name.replace("_", "")) for key in keys)
    ]

###############################################################################
def _single_frame_scope_warning(
    request: ExecuteCapabilityInput, coverage: dict[str, Any]
) -> str | None:
    """Warn when one raster frame stands in for a window or an aggregation."""

    def day(value: object) -> date | None:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    start = day(request.start_time_iso)
    end = day(request.end_time_iso)
    aggregation = str(request.arguments.get("aggregation") or "").strip()
    multi_day = start is not None and end is not None and end > start
    if not multi_day and not aggregation:
        return None
    frame = day(coverage.get("time")) or start
    shown = frame.isoformat() if frame else "a single date"
    return (
        f"Only one frame, dated {shown}, is shown; "
        "no aggregation was applied over the requested period."
    )


###############################################################################
def _response_summary(
    response: ProviderResponse,
    *,
    request: ExecuteCapabilityInput | None = None,
    location: ResolvedLocation | None = None,
) -> dict[str, Any]:
    payload = response.payload
    features = payload.get("features")
    summary: dict[str, Any] = {
        "capability_id": response.capability_id,
        "provider_id": response.provider_id,
        "result_status": response.result_status,
        "result_type": response.result_type,
        "feature_count": len(features) if is_json_array(features) else None,
        "map_eligibility": _map_eligibility(response),
        "stale": response.stale,
        "fetched_at": response.fetched_at.isoformat(),
    }
    feature_bbox = _feature_bbox(features)
    if feature_bbox is not None:
        summary["bbox"] = feature_bbox
    if response.result_type == "features" and is_json_array(features):
        feature_preview = _feature_preview(features)
        if feature_preview:
            summary["feature_preview"] = feature_preview
            summary["feature_preview_limit"] = 10
            summary["feature_preview_truncated"] = len(features) > len(feature_preview)
    record_fields = _record_fields(features, payload)
    if record_fields:
        summary["record_fields"] = record_fields
    if response.attribution:
        summary["attribution"] = [str(item)[:200] for item in response.attribution[:8]]
    if response.warnings:
        summary["warnings"] = [str(item)[:300] for item in response.warnings[:8]]
    if response.observation_time:
        summary["observation_time"] = response.observation_time
    if response.spatial_resolution:
        summary["spatial_resolution"] = response.spatial_resolution
    if response.units:
        summary["units"] = dict(list(response.units.items())[:16])
    if response.coverage:
        summary["coverage"] = dict(list(response.coverage.items())[:16])
    if response.source_url:
        summary["source_url"] = response.source_url[:500]
    if response.partial:
        summary["partial"] = True
    yearly_kwh_per_kwp = payload.get("yearlyKwhPerKwpEstimate")
    if isinstance(yearly_kwh_per_kwp, (int, float)) and not isinstance(
        yearly_kwh_per_kwp, bool
    ):
        summary["solar_potential"] = {
            "yearly_kwh_per_kwp": float(yearly_kwh_per_kwp),
            "unit": "kWh/kWp/year",
        }
    facts = payload.get("facts")
    if payload.get("kind") == "place_facts" and is_json_object(facts):
        summary["facts"] = dict(list(facts.items())[:16])
    window_summary = payload.get("window_summary")
    if is_json_object(window_summary):
        summary["window_summary"] = window_summary
    if payload.get("kind") == "weather_forecast" and payload.get("current_in_window") is not False:
        current = payload.get("current")
        if is_json_object(current):
            observations = {
                key: current[key]
                for key in (
                    "temperature_2m",
                    "precipitation",
                    "weather_code",
                    "relative_humidity_2m",
                    "surface_pressure",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "wind_gusts_10m",
                )
                if key in current
            }
            if observations:
                # Keep current weather values available for bounded answer
                # synthesis without exposing the complete provider payload.
                summary["observations"] = observations
    if payload.get("kind") in {"weather_forecast", "air_quality_forecast"}:
        kind = str(payload.get("kind"))
        summary["kind"] = kind
        hourly = payload.get("hourlyForecast")
        if is_json_array(hourly):
            requested = _requested_attributes(request)
            base_fields = (
                (
                    "time",
                    "temperature_2m",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                    "surface_pressure",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "wind_gusts_10m",
                )
                if payload.get("kind") == "weather_forecast"
                else (
                    "time",
                    "pm10",
                    "pm2_5",
                    "carbon_monoxide",
                    "nitrogen_dioxide",
                    "ozone",
                    "sulphur_dioxide",
                )
            )
            fields = (*base_fields, *(name for name in requested if name not in base_fields))
            summary["requested_fields"] = [
                name for name in fields[len(base_fields):]
                if any(is_json_object(row) and name in row for row in hourly)
            ]
            timezone = payload.get("timezone")
            try:
                timezone_info = (
                    ZoneInfo(timezone) if isinstance(timezone, str) else UTC
                )
            except (ZoneInfoNotFoundError, ValueError):
                timezone_info = None
            selected_rows: list[dict[str, Any]] = []
            windowed = is_json_object(window_summary)
            if windowed:
                # The provider already restricted the hours to the requested
                # window; a rolling window from now would answer another day.
                selected_rows = [row for row in hourly if is_json_object(row)][:WINDOW_HOURS_LIMIT]
            elif timezone_info is not None:
                window_start = response.fetched_at.astimezone(timezone_info)
                window_end = window_start + timedelta(hours=24)
                for raw_row in hourly:
                    if not is_json_object(raw_row) or not raw_row.get("time"):
                        continue
                    try:
                        row_time = datetime.fromisoformat(
                            str(raw_row["time"]).replace("Z", "+00:00")
                        )
                    except ValueError:
                        continue
                    if row_time.tzinfo is None:
                        row_time = row_time.replace(tzinfo=timezone_info)
                    else:
                        row_time = row_time.astimezone(timezone_info)
                    if window_start <= row_time < window_end:
                        selected_rows.append(raw_row)
                    if len(selected_rows) == 24:
                        break
            rows = [
                {key: row[key] for key in fields if key in row}
                for row in selected_rows
            ]
            window_hours = (
                int(window_summary.get("hours") or 0) if is_json_object(window_summary) else 24
            )
            summary["forecast_hours_requested"] = window_hours
            summary["forecast_hours"] = len(rows)
            summary["forecast_truncated"] = len(rows) < window_hours
            summary["forecast_window_status"] = (
                "ok" if len(rows) == min(window_hours, WINDOW_HOURS_LIMIT) else "partial"
            )
            if rows:
                summary["hourly_forecast"] = rows
                summary["forecast_window_start"] = rows[0].get("time")
                summary["forecast_window_end"] = rows[-1].get("time")
        timezone = payload.get("timezone")
        if isinstance(timezone, str) and timezone:
            summary["timezone"] = timezone[:80]
    if request is not None:
        # Keep the semantic query visible to the model without exposing the
        # provider payload or trusting model-owned geometry/time fields.
        summary["query"] = {
            "operation": request.operation,
            "location_ref": request.location_ref,
            "resolved_location": location.label if location is not None else None,
            "bbox": list(request.bbox) if request.bbox is not None else None,
            "radius_m": request.radius_m,
            "start_time_iso": request.start_time_iso,
            "end_time_iso": request.end_time_iso,
            "filter_keys": sorted(str(key) for key in request.filters)[:32],
        }
    return summary


###############################################################################
def _record_fields(features: Any, payload: dict[str, Any]) -> str:
    """Field names a later evidence transform may sort or filter on.

    Feature results expose their property names; a single-object result
    exposes its numeric fields, nested ones by dotted path.
    """

    if is_json_array(features):
        names = {
            key
            for feature in features[:50]
            if is_json_object(feature) and is_json_object(feature.get("properties"))
            for key, value in feature["properties"].items()
            if isinstance(value, (str, int, float)) and not isinstance(value, bool)
        }
    else:
        names = {
            key
            for key, value in with_nested_scalars(payload).items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    return ", ".join(sorted(names))[:300]

###############################################################################
def _feature_preview(features: list[Any]) -> list[dict[str, Any]]:
    """Expose a small, allowlisted feature sample for bounded answer synthesis."""

    preview: list[dict[str, Any]] = []
    for feature in features[:10]:
        if not is_json_object(feature):
            continue
        properties = feature.get("properties")
        values = properties if is_json_object(properties) else feature
        item: dict[str, Any] = {}
        for key in ("id", "name", "category", "latitude", "longitude", "address"):
            value = values.get(key, feature.get(key))
            if isinstance(value, (str, int, float)):
                item[key] = value[:160] if isinstance(value, str) else value
        metadata = values.get("metadata")
        distance = values.get("distance_m")
        if distance is None and is_json_object(metadata):
            distance = metadata.get("distance_m")
        if isinstance(distance, (int, float)):
            item["distance_m"] = distance
        geometry = feature.get("geometry")
        coordinates = geometry.get("coordinates") if is_json_object(geometry) else None
        if (
            "latitude" not in item
            and "longitude" not in item
            and is_json_array(coordinates)
            and len(coordinates) >= 2
            and isinstance(coordinates[0], (int, float))
            and isinstance(coordinates[1], (int, float))
        ):
            item["longitude"], item["latitude"] = coordinates[:2]
        if item:
            preview.append(item)
    return preview

###############################################################################
def _map_eligibility(response: ProviderResponse) -> str:
    """Classify provider evidence before it is admitted to a map plan."""

    if response.result_status == "valid_empty":
        return "not_renderable"

    payload = response.payload
    features = payload.get("features")
    if is_json_array(features):
        if any(_feature_has_geometry(item) for item in features):
            return "renderable"
        return "not_renderable"

    if response.result_type == "raster" and _has_render_source(payload):
        return "renderable"

    render = payload.get("render")
    if is_json_object(render) and _has_render_source(render):
        return "renderable"

    if response.result_type == "metadata":
        return "not_renderable"
    return "unknown"

###############################################################################
def _feature_has_geometry(value: object) -> bool:
    feature = value if is_json_object(value) else {}
    geometry = feature.get("geometry")
    if is_json_object(geometry):
        return bool(geometry.get("type")) and (
            geometry.get("coordinates") is not None
            or geometry.get("geometries") is not None
        )
    latitude = feature.get("latitude")
    longitude = feature.get("longitude")
    return (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
    )

###############################################################################
def _has_render_source(value: object) -> bool:
    payload = value if is_json_object(value) else {}
    mode = str(
        payload.get("renderingMode")
        or payload.get("rendering_mode")
        or ""
    ).strip().casefold()
    if mode in {"metadata-only", "metadata_only"}:
        return False
    return any(
        isinstance(payload.get(key), str) and payload[key].strip()
        for key in (
            "url",
            "tileUrl",
            "tile_url_template",
            "tileUrlTemplate",
            "url_template",
            "serviceUrl",
            "service_url",
            "featuresUrl",
            "features_url",
        )
    )

###############################################################################
def _feature_bbox(value: object) -> list[float] | None:
    if not is_json_array(value):
        return None
    coordinates: list[tuple[float, float]] = []
    for raw_feature in value:
        feature = raw_feature if is_json_object(raw_feature) else {}
        latitude = feature.get("latitude")
        longitude = feature.get("longitude")
        if (
            isinstance(latitude, (int, float))
            and not isinstance(latitude, bool)
            and isinstance(longitude, (int, float))
            and not isinstance(longitude, bool)
        ):
            coordinates.append((float(longitude), float(latitude)))
            continue
        geometry = feature.get("geometry")
        if is_json_object(geometry):
            for longitude, latitude in _geometry_positions(geometry):
                coordinates.append((longitude, latitude))
    if not coordinates:
        return None
    longitudes = [item[0] for item in coordinates]
    latitudes = [item[1] for item in coordinates]
    return [min(longitudes), min(latitudes), max(longitudes), max(latitudes)]

###############################################################################
def _geometry_positions(value: object) -> list[tuple[float, float]]:
    """Extract coordinate pairs from any bounded GeoJSON geometry."""

    geometry = value if is_json_object(value) else {}
    if geometry.get("type") == "GeometryCollection":
        geometries = geometry.get("geometries")
        if not is_json_array(geometries):
            return []
        positions: list[tuple[float, float]] = []
        for item in geometries:
            positions.extend(_geometry_positions(item))
        return positions
    coordinates = geometry.get("coordinates")
    positions: list[tuple[float, float]] = []

    def visit(value: object) -> None:
        if is_json_array(value):
            if (
                len(value) >= 2
                and isinstance(value[0], (int, float))
                and not isinstance(value[0], bool)
                and isinstance(value[1], (int, float))
                and not isinstance(value[1], bool)
            ):
                positions.append((float(value[0]), float(value[1])))
                return
            for item in value:
                visit(item)

    visit(coordinates)
    return positions

###############################################################################
def _summary_text(response: ProviderResponse, summary: dict[str, Any]) -> str:
    count = summary.get("feature_count")
    if response.result_status == "valid_empty":
        return f"Capability '{response.capability_id}' returned no matching data."
    if isinstance(count, int):
        return (
            f"Capability '{response.capability_id}' returned {count} feature(s) "
            f"from provider '{response.provider_id}'."
        )
    return (
        f"Capability '{response.capability_id}' returned a "
        f"{response.result_type} result from provider '{response.provider_id}'."
    )

###############################################################################
def _json_size(value: Any) -> int | None:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return None

###############################################################################
def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


__all__ = ["CapabilityExecutionService", "ToolExecutionContext"]
