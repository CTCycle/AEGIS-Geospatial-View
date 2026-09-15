"""Native provider-layer discovery handler."""

from __future__ import annotations

import time

from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
)
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.services.agent.tool_definitions import ProviderLayerDiscoveryInput
from server.services.geospatial.api_service import (
    GeospatialApiService,
    GeospatialApiServiceError,
    GeospatialCapabilityNotFoundError,
)


###############################################################################
class ProviderLayerToolHandler:
    """Discover provider-native layers through the canonical tool boundary."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        geospatial_api_service: GeospatialApiService,
        evidence_repository: AgentEvidenceRepository,
    ) -> None:
        self.geospatial_api_service = geospatial_api_service
        self.evidence_repository = evidence_repository

    # -------------------------------------------------------------------------
    async def discover(
        self,
        request: ProviderLayerDiscoveryInput,
        state: AgentRunState,
    ) -> ToolResult:
        started = time.perf_counter()
        offset = _cursor_offset(request.cursor)
        try:
            # The provider API has a bounded metadata ceiling. Fetch the
            # complete bounded page before applying the model-facing cursor so
            # pagination remains deterministic for a query/provider pair.
            response = await self.geospatial_api_service.list_provider_layers(
                request.provider_id,
                query=request.query,
                limit=250,
                refresh=request.refresh,
            )
        except GeospatialCapabilityNotFoundError as exc:
            return _failure(
                provider_id=request.provider_id,
                code="provider_not_found",
                message=str(exc),
                recovery="choose_alternate_tool",
                started=started,
            )
        except GeospatialApiServiceError as exc:
            return _failure(
                provider_id=request.provider_id,
                code="provider_unavailable",
                message=str(exc),
                recovery="replan",
                started=started,
            )

        payload = response.model_dump(mode="json")
        layers = payload.get("layers")
        all_layers = layers if isinstance(layers, list) else []
        page = all_layers[offset : offset + request.limit]
        next_offset = offset + len(page)
        next_cursor = str(next_offset) if next_offset < len(all_layers) else None
        page_payload = {
            "provider": payload.get("provider", request.provider_id),
            "layers": page,
            "next_cursor": next_cursor,
            "total": len(all_layers),
            "warnings": payload.get("warnings", []),
        }
        evidence = self.evidence_repository.create(
            conversation_id=state.conversation_id,
            run_id=state.run_id,
            kind="provider_layer_descriptor",
            media_type="application/json",
            status="available" if all_layers else "valid_empty",
            payload=payload,
            summary={
                "provider_id": request.provider_id,
                "layer_count": len(all_layers),
                "map_eligibility": "renderable" if all_layers else "not_renderable",
            },
            provenance={
                "provider_id": request.provider_id,
                "query": request.query,
                "refresh": request.refresh,
            },
        )
        evidence_ref = str(evidence.evidence_id)
        if evidence_ref not in state.evidence_refs:
            state.evidence_refs.append(evidence_ref)
        status = "success" if page else "valid_empty"
        return ToolResult(
            call_id="handler-call",
            tool_name="discover_geospatial_provider_layers",
            status=status,
            summary=(
                f"Found {len(page)} provider-native layers for {request.provider_id}."
                if page
                else f"No provider-native layers matched {request.provider_id}."
            ),
            data={
                **page_payload,
                "evidence_ref": evidence_ref,
            },
            evidence_refs=[evidence_ref],
            metadata=ToolExecutionMetadata(
                provider_id=request.provider_id,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                evidence_refs=[evidence_ref],
            ),
        )


###############################################################################
def _cursor_offset(cursor: str | None) -> int:
    if cursor is None or not cursor.strip():
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


###############################################################################
def _failure(
    *,
    provider_id: str,
    code: str,
    message: str,
    recovery: str,
    started: float,
) -> ToolResult:
    return ToolResult(
        call_id="handler-call",
        tool_name="discover_geospatial_provider_layers",
        status="failed",
        summary=message,
        error=ToolExecutionError(
            error_type=(
                "state_conflict"
                if code == "provider_not_found"
                else "provider_unavailable"
            ),
            code=code,
            message=message,
            retryable=False,
            recovery=recovery,  # type: ignore[arg-type]
        ),
        metadata=ToolExecutionMetadata(
            provider_id=provider_id,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        ),
    )


__all__ = ["ProviderLayerToolHandler"]
