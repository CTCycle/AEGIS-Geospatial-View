"""Canonical provider-backed capability execution for native-v2 tools."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from server.domain.agent.evidence import EvidenceKind, EvidenceStatus
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.domain.geospatial.providers import ProviderRequest, ProviderResponse
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.geospatial.capability_registry import CapabilityRegistry
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
)
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
class EvidenceStore(Protocol):
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
    ``ProviderRegistry``.  This service only performs capability/runtime
    checks, builds the provider-neutral request, persists complete evidence,
    and returns a bounded model-facing summary.
    """

    TOOL_NAME = "execute_geospatial_capability"

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
    ) -> ToolResult:
        started = time.perf_counter()
        capability_id = request.capability_id

        try:
            manifest = self.capability_registry.get_capability(capability_id)
        except Exception:
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
        except Exception:
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

        provider_request = ProviderRequest(
            capability_id=capability_id,
            bbox=_bbox(request.bbox),
            time=request_time,
            params=_provider_params(request),
        )
        try:
            response = await self.provider_registry.fetch(
                provider_id,
                provider_request,
            )
            if not isinstance(response, ProviderResponse):
                raise ProviderMalformedPayloadError(
                    "Provider returned an invalid normalized response."
                )
        except Exception as exc:
            return self._provider_failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error=exc,
            )

        status = _tool_status(response)
        summary = _response_summary(response)
        try:
            evidence_ref = self._persist_evidence(
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
            ),
        )

    # -------------------------------------------------------------------------
    def _persist_evidence(
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
            record = repository.create(
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
                },
                parent_evidence_ids=list(request.evidence_refs),
            )
            return str(getattr(record, "evidence_id", "")).strip() or None
        except Exception as exc:
            raise ProviderMalformedPayloadError(
                "Normalized provider evidence could not be persisted."
            ) from exc

    # -------------------------------------------------------------------------
    def _provider_failure(
        self,
        *,
        context: ToolExecutionContext,
        capability_id: str,
        provider_id: str,
        started: float,
        error: Exception,
    ) -> ToolResult:
        if isinstance(error, ProviderInvalidQueryError):
            return self._failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error_type="semantic_validation",
                code="provider_invalid_query",
                message="The provider rejected the validated query.",
                recovery="correct_arguments",
                retryable=True,
            )
        if isinstance(error, ProviderAuthError):
            return self._failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error_type="authentication",
                code="provider_authentication",
                message="Provider authentication is unavailable.",
                recovery="choose_alternate_tool",
            )
        if isinstance(error, ProviderRateLimitError):
            return self._failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error_type="rate_limit",
                code="provider_rate_limit",
                message="The provider rate limit was reached.",
                recovery="choose_alternate_tool",
            )
        if isinstance(error, ProviderTimeoutError):
            return self._failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error_type="timeout",
                code="provider_timeout",
                message="The provider did not respond within its execution deadline.",
                recovery="replan",
                timeout_origin="provider_transport",
            )
        if isinstance(error, ProviderMalformedPayloadError):
            return self._failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error_type="provider_malformed_response",
                code="provider_malformed_response",
                message="The provider response could not be normalized or stored.",
                recovery="choose_alternate_tool",
            )
        if isinstance(
            error,
            (
                ProviderCircuitOpenError,
                ProviderUnavailableError,
                ProviderNotRegisteredError,
                ProviderError,
            ),
        ):
            return self._failure(
                context=context,
                capability_id=capability_id,
                provider_id=provider_id,
                started=started,
                error_type="provider_unavailable",
                code="provider_unavailable",
                message="The provider is temporarily unavailable.",
                recovery="choose_alternate_tool",
            )
        return self._failure(
            context=context,
            capability_id=capability_id,
            provider_id=provider_id,
            started=started,
            error_type="internal_error",
            code="capability_execution_failed",
            message="The capability failed during execution.",
            recovery="terminal",
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
            error=error,
            metadata=ToolExecutionMetadata(
                capability_id=capability_id,
                provider_id=provider_id,
                duration_ms=_duration_ms(started),
            ),
        )


def _provider_id(manifest: dict[str, Any]) -> str:
    return str(manifest.get("provider") or manifest.get("provider_id") or "").strip()


def _bbox(value: list[float] | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    return tuple(float(item) for item in value)  # type: ignore[return-value]


def _provider_params(request: ExecuteCapabilityInput) -> dict[str, Any]:
    params = dict(request.arguments)
    if request.operation is not None:
        params.setdefault("operation", request.operation)
    if request.location_ref is not None:
        params.setdefault("location_ref", request.location_ref)
    if request.evidence_refs:
        params.setdefault("evidence_refs", list(request.evidence_refs))
    if request.radius_m is not None:
        params.setdefault("radius_m", request.radius_m)
    if request.filters:
        params["filters"] = dict(request.filters)
    if request.end_time_iso is not None:
        params.setdefault("end_time_iso", request.end_time_iso)
    return params


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


def _tool_status(response: ProviderResponse) -> Any:
    if response.result_status == "valid_empty":
        return "valid_empty"
    if response.result_status in {"partial", "stale"} or response.partial:
        return "partial"
    return "success"


def _evidence_status(response: ProviderResponse) -> EvidenceStatus:
    if response.result_status == "valid_empty":
        return "valid_empty"
    if response.result_status in {"partial", "stale"} or response.partial:
        return "partial"
    return "available"


def _evidence_kind(result_type: str) -> EvidenceKind:
    if result_type == "features":
        return "vector"
    if result_type == "raster":
        return "raster_descriptor"
    return "capability_result"


def _response_summary(response: ProviderResponse) -> dict[str, Any]:
    payload = response.payload
    features = payload.get("features")
    summary: dict[str, Any] = {
        "capability_id": response.capability_id,
        "provider_id": response.provider_id,
        "result_status": response.result_status,
        "result_type": response.result_type,
        "feature_count": len(features) if isinstance(features, list) else None,
        "stale": response.stale,
    }
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
    return summary


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


def _json_size(value: Any) -> int | None:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return None


def _duration_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


__all__ = ["CapabilityExecutionService", "ToolExecutionContext"]
