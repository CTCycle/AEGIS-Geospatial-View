from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

import json
import math
from typing import Any, cast

from server.domain.agent.catalog import (
    CATALOG_PAGE_LIMIT,
    CapabilityCatalogFilter,
    GeospatialCapabilityExecutionResult,
)
from server.domain.agent.decision import (
    ClarificationRequest,
    ExecutionPlan,
    ResolvedLocation,
)
from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.evidence import AgentEvidenceEnvelope
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.domain.agent.interpretation import normalize_target_key
from server.contracts.extraction import (
    LocationSignal,
    LocationSignalType,
    TurnParseResult,
)
from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    OverlayInstance,
    ProviderLayerSelection,
)
from server.domain.agent.policies import ToolAuthorizationResult
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.overlay_collection import OverlayCollectionService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.types import LLMToolDefinition
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

###############################################################################
class CapabilityArgumentSchemaError(ValueError):
    """Raised when a catalog capability cannot be validated for execution."""


###############################################################################
class AgentToolCatalogService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        runtime_registry: RuntimeRegistry,
        search_orchestrator: LocationSearchOrchestrator | None = None,
        request_builder: RequestBuilder | None = None,
        location_resolver: LocationResolver | None = None,
        tool_registry: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        geospatial_api_service: GeospatialApiService,
        evidence_repository: AgentEvidenceRepository | None = None,
    ) -> None:
        self.capability_registry = capability_registry
        self.runtime_registry = runtime_registry
        self.search_orchestrator = search_orchestrator
        self.request_builder = request_builder or RequestBuilder()
        self.location_resolver = location_resolver or LocationResolver()
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.geospatial_api_service = geospatial_api_service
        self.evidence_repository = evidence_repository

    # -------------------------------------------------------------------------
    def build_native_tools(
        self,
        context: AgentExecutionContext | None = None,
    ) -> list[LLMToolDefinition]:
        metadata: dict[str, Any] = context.metadata if context is not None else {}
        allowed_tool_names = set(map(str, metadata.get("allowed_native_tools") or []))
        allowed_capability_ids = sorted(
            set(map(str, metadata.get("allowed_capability_ids") or []))
        )
        evidence_refs = [
            str(item)
            for item in cast(list[Any], metadata.get("evidence_refs") or [])
        ]
        presentation_required = bool(metadata.get("presentation_required"))
        unresolved_targets = bool(metadata.get("unresolved_targets"))
        definitions = [
            LLMToolDefinition(
                name="resolve_geospatial_location",
                description=(
                    "Resolve one unresolved canonical geographic target. Use only a target_id "
                    "from the canonical request or a candidate ID returned by this tool; "
                    "never geocode arbitrary replacement text."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "target_id": {"type": "string"},
                        "expected_location_type": {"type": ["string", "null"]},
                        "candidate_id": {"type": ["string", "null"]},
                    },
                    "required": ["target_id"],
                },
            ),
            LLMToolDefinition(
                name="list_geospatial_capabilities",
                description=(
                    "Discover enabled geospatial capabilities before selecting an unknown "
                    "basemap, overlay, direct tool, or catalog action. Use filters to "
                    "narrow discovery; this tool does not execute a capability."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "query": {
                            "type": ["string", "null"],
                            "description": "Optional text or concept to match against catalog identity and description.",
                        },
                        "category": {
                            "type": ["string", "null"],
                            "description": "Optional catalog category such as basemap, overlay, or tool.",
                        },
                        "geometry_type": {
                            "type": ["string", "null"],
                            "description": "Optional geometry filter when the requested data shape is known.",
                        },
                        "capability_domain": {
                            "type": ["string", "null"],
                            "description": "Optional capability domain such as discovery, analysis, or presentation.",
                        },
                        "temporal_support": {
                            "type": ["string", "null"],
                            "description": "Optional temporal support filter such as static, current, or historical.",
                        },
                        "analysis_operation": {
                            "type": ["string", "null"],
                            "description": "Optional operation filter such as point-query, proximity, or aggregate.",
                        },
                        "renderable": {
                            "type": ["boolean", "null"],
                            "description": "Optional renderability filter.",
                        },
                        "bbox": {
                            "type": ["array", "null"],
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                            "description": "Optional west, south, east, north extent for spatial discovery.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": CATALOG_PAGE_LIMIT,
                            "description": "Page size; use the returned cursor to continue discovery.",
                        },
                        "cursor": {
                            "type": ["string", "null"],
                            "description": "Cursor returned by a previous catalog page.",
                        },
                    },
                },
            ),
            LLMToolDefinition(
                name="describe_geospatial_capability",
                description=(
                    "Inspect one exact capability ID after discovery when its manifest, "
                    "rendering mode, provider metadata, or executable argument schema is "
                    "needed. Do not guess an ID or use this for execution."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"capability_id": {"type": "string"}},
                    "required": ["capability_id"],
                },
            ),
            LLMToolDefinition(
                name="execute_geospatial_capability",
                description=(
                    "Request execution of one already-selected, policy-allowlisted "
                    "manifest capability by exact capability_id. AEGIS supplies the "
                    "canonical target and validated arguments from the deterministic "
                    "plan; do not invent target IDs, coordinates, or provider arguments."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "capability_id": {
                            "type": "string",
                            "description": "Exact stable capability ID from catalog discovery or the routed plan.",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Optional model hints; the application-owned plan is authoritative.",
                        },
                        "location_ref": {
                            "type": ["string", "null"],
                            "description": "Optional canonical location reference returned by location resolution.",
                        },
                        "input_evidence_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 16,
                        },
                    },
                    "required": ["capability_id"],
                },
            ),
            LLMToolDefinition(
                name="fetch_geospatial_provider_layers",
                description=(
                    "Discover normalized provider-native layers only for an explicitly "
                    "routed and policy-allowlisted provider when the catalog does not "
                    "already identify the requested layer. This does not render a layer."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "provider_id": {
                            "type": "string",
                            "description": "Exact routed provider ID, for example gibs.",
                        },
                        "query": {
                            "type": ["string", "null"],
                            "description": "Optional material query refinement for provider-native layer discovery.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 250,
                            "default": 50,
                        },
                        "refresh": {
                            "type": "boolean",
                            "description": "Refresh provider metadata only when cached discovery is insufficient.",
                            "default": False,
                        },
                    },
                    "required": ["provider_id"],
                },
            ),
            LLMToolDefinition(
                name="inspect_geospatial_evidence",
                description=(
                    "Inspect bounded metadata, schema, samples, statistics, or a page from "
                    "stored evidence. Full provider payloads are never returned by default."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "evidence_ref": {"type": "string"},
                        "view": {
                            "type": "string",
                            "enum": ["metadata", "schema", "sample", "statistics", "page"],
                        },
                        "fields": {"type": "array", "items": {"type": "string"}, "maxItems": 32},
                        "cursor": {"type": ["string", "null"]},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["evidence_ref", "view"],
                },
            ),
            LLMToolDefinition(
                name="transform_geospatial_evidence",
                description=(
                    "Transform normalized vector or tabular evidence using up to eight "
                    "declarative filters, sorts, projections, limits, or aggregates. "
                    "Arbitrary expressions and raster transformation are not supported."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "evidence_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
                        "operations": {"type": "array", "items": {"type": "object"}, "minItems": 1, "maxItems": 8},
                    },
                    "required": ["evidence_refs", "operations"],
                },
            ),
            LLMToolDefinition(
                name="prepare_geospatial_map",
                description=(
                    "Prepare a candidate map from validated locations, provider descriptors, "
                    "or renderable evidence. Preparation does not make the map visible; the "
                    "browser render acknowledgement is authoritative."
                ),
                parameters_json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "evidence_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 16},
                        "location_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 16},
                        "basemap_id": {"type": ["string", "null"]},
                        "layer_options": {"type": "object"},
                        "viewport_strategy": {"type": "string", "enum": ["fit_results", "fit_location", "preserve_current"]},
                    },
                    # At least one of these collections is required by the
                    # handler, but JSON Schema cannot express that union
                    # without making the model provide an unnecessary empty
                    # value.  Keep both optional and enforce the invariant in
                    # the deterministic boundary below.
                    "required": [],
                },
            ),
        ]
        if allowed_capability_ids:
            execute = next(
                item
                for item in definitions
                if item.name == "execute_geospatial_capability"
            )
            execute.parameters_json_schema["properties"]["capability_id"]["enum"] = (
                allowed_capability_ids
            )
        if context is not None:
            context.metadata["tool_exposure_reasons"] = {
                "resolve_geospatial_location": "Canonical target remains unresolved.",
                "list_geospatial_capabilities": "No exact capability is trusted or discovery is still useful.",
                "describe_geospatial_capability": "Exact capability metadata or argument schema is needed.",
                "execute_geospatial_capability": "Policy produced an exact allowlisted capability ID.",
                "fetch_geospatial_provider_layers": "Provider-native discovery is explicitly routed and allowed.",
                "inspect_geospatial_evidence": "Usable stored evidence is available for bounded inspection.",
                "transform_geospatial_evidence": "Usable normalized evidence can satisfy a pending transformation.",
                "prepare_geospatial_map": "Geographic presentation is required and a renderable input exists.",
            }
            if allowed_tool_names:
                definitions = [item for item in definitions if item.name in allowed_tool_names]
            # Once deterministic planning has produced an exact capability
            # allowlist, discovery is no longer part of this native turn.  A
            # model may choose that planned capability and the server binds
            # its canonical target/arguments; exposing another catalog loop
            # only creates an unbounded provider round-trip and can cause the
            # model to re-list the same page instead of executing the plan.
            if allowed_capability_ids and not metadata.get("allow_capability_discovery"):
                definitions = [
                    item
                    for item in definitions
                    if item.name
                    not in {"list_geospatial_capabilities", "describe_geospatial_capability"}
                ]
            if not allowed_capability_ids and not metadata.get("register_all"):
                definitions = [item for item in definitions if item.name != "execute_geospatial_capability"]
            # Location resolution is an application-owned transition.  The
            # model must never be asked to invent or choose an internal
            # target_id; registration retains the handler for deterministic
            # compatibility tests, but real runs do not expose the tool.
            if not metadata.get("register_all"):
                definitions = [item for item in definitions if item.name != "resolve_geospatial_location"]
            elif not unresolved_targets:
                definitions = [item for item in definitions if item.name != "resolve_geospatial_location"]
            if not evidence_refs:
                definitions = [
                    item
                    for item in definitions
                    if item.name not in {"inspect_geospatial_evidence", "transform_geospatial_evidence"}
                ]
            # Map preparation is a post-evidence transition.  A resolved
            # location alone is not a renderable input for the native loop:
            # the deterministic plan must execute its canonical basemap or
            # provider step first.  Exposing preparation earlier lets a model
            # select it before the planned execution and creates a recoverable
            # but unnecessary provider round-trip.  A server-side prepared
            # candidate is also sufficient when the evidence reference is
            # intentionally kept out of the model envelope.
            if not presentation_required or (
                not evidence_refs and not metadata.get("prepared_map_session")
            ):
                definitions = [item for item in definitions if item.name != "prepare_geospatial_map"]
        return definitions

    # -------------------------------------------------------------------------
    def register_with(self, registry: ToolRegistry) -> None:
        # Registration owns the complete canonical surface; exposure is
        # recalculated per run by ``build_native_tools(context)``.
        registration_context = AgentExecutionContext(
            metadata={
                "unresolved_targets": True,
                "evidence_refs": ["registration"],
                "register_all": True,
                "presentation_required": True,
                "resolved_location": True,
            }
        )
        for definition in self.build_native_tools(registration_context):
            if definition.name == "resolve_geospatial_location":
                registry.register_native_tool(definition, self._resolve_location_tool_handler)
            elif definition.name == "list_geospatial_capabilities":
                registry.register_native_tool(definition, self._list_tool_handler)
            elif definition.name == "describe_geospatial_capability":
                registry.register_native_tool(definition, self._describe_tool_handler)
            elif definition.name == "execute_geospatial_capability":
                registry.register_native_tool(definition, self._execute_tool_handler)
            elif definition.name == "fetch_geospatial_provider_layers":
                registry.register_native_tool(
                    definition, self._provider_layers_tool_handler
                )
            elif definition.name == "inspect_geospatial_evidence":
                registry.register_native_tool(definition, self._inspect_evidence_tool_handler)
            elif definition.name == "transform_geospatial_evidence":
                registry.register_native_tool(definition, self._transform_evidence_tool_handler)
            elif definition.name == "prepare_geospatial_map":
                registry.register_native_tool(definition, self._prepare_map_tool_handler)

    # -------------------------------------------------------------------------
    async def _list_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        result = self.list_geospatial_capabilities(CapabilityCatalogFilter(**arguments))
        discovered = {
            str(item.get("id"))
            for item in result.get("items", [])
            if is_json_object(item) and item.get("id")
        }
        if discovered:
            already_discovered = set(
                map(str, context.metadata.get("discovered_capability_ids") or [])
            )
            already_discovered.update(discovered)
            context.metadata["discovered_capability_ids"] = sorted(already_discovered)
            current = set(
                map(str, context.metadata.get("allowed_capability_ids") or [])
            )
            current.update(discovered)
            context.metadata["allowed_capability_ids"] = sorted(current)
            context.policy_constraints["allowed_capability_ids"] = sorted(current)
        return result

    # -------------------------------------------------------------------------
    async def _describe_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        capability_id = str(arguments["capability_id"])
        discovered = set(
            map(str, context.metadata.get("discovered_capability_ids") or [])
        )
        allowlisted = set(
            map(str, context.metadata.get("allowed_capability_ids") or [])
        )
        if capability_id not in discovered and capability_id not in allowlisted:
            raise ValueError(
                f"Capability '{capability_id}' was not returned by an allowed discovery call."
            )
        return self.describe_geospatial_capability(capability_id)

    # -------------------------------------------------------------------------
    async def _resolve_location_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        target_id = str(arguments.get("target_id") or "").strip()
        canonical = context.canonical_request
        target = canonical.target(target_id) if canonical is not None and target_id else None
        if target is None:
            return AgentEvidenceEnvelope(
                ok=False,
                status="error",
                error={"code": "unknown_target", "message": "Only a canonical target may be resolved."},
            ).model_dump(mode="json")
        if target.resolved_location is not None:
            location = target.resolved_location
            return self._location_envelope(location, context, target_id)
        parsed_request = self._parsed_request_from_context(context)
        signals = [
            signal
            for signal in (
                parsed_request.location_signals if parsed_request is not None else []
            )
            if getattr(signal, "target_id", None) in {None, target_id}
        ]
        if not signals:
            raw = str(getattr(target, "original_text", "") or "").strip()
            if raw:
                signals = self._build_argument_location_signals({"location": raw})
        result = await self.location_resolver.resolve_location_signals(
            signals, json_object(context.map_state)
        )
        if isinstance(result, ClarificationRequest):
            return AgentEvidenceEnvelope(
                ok=False,
                status="error",
                error={"code": "ambiguous", "message": result.question},
                summary={"candidates": result.model_dump(mode="json")},
            ).model_dump(mode="json")
        return self._location_envelope(result, context, target_id)

    # -------------------------------------------------------------------------
    def _location_envelope(
        self,
        location: ResolvedLocation,
        context: AgentExecutionContext,
        target_id: str,
    ) -> dict[str, Any]:
        canonical = context.canonical_request
        if canonical is not None:
            target = canonical.target(target_id)
            if target is not None:
                target.resolved_location = location
                target.resolution_status = "resolved"
            context.metadata["unresolved_targets"] = any(
                item.resolved_location is None for item in canonical.targets
            )
        context.metadata["resolved_location"] = location.model_dump(mode="json")
        payload = location.model_dump(mode="json")
        evidence_ref = self._persist_evidence(
            context=context,
            kind="location",
            media_type="application/json",
            status="available",
            payload=payload,
            summary={
                "label": location.label,
                "target_id": target_id,
                "coordinates": [location.longitude, location.latitude],
                "map_eligibility": "renderable",
            },
            provenance=location.provenance.model_dump(mode="json") if location.provenance else {},
        )
        return AgentEvidenceEnvelope(
            ok=True,
            status="available",
            evidence_ref=evidence_ref,
            summary={
                "target_id": target_id,
                "label": location.label,
                "type": location.location_type,
                "coordinates": [location.longitude, location.latitude],
                "bounds": location.bbox,
                "confidence": location.confidence,
            },
            provenance=location.provenance.model_dump(mode="json") if location.provenance else {},
            map_eligibility="renderable",
            state_changes=[{"type": "location_resolved", "target_id": target_id}],
        ).model_dump(mode="json")

    # -------------------------------------------------------------------------
    async def _execute_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        payload = dict(
            await self.execute_geospatial_capability(
                str(arguments["capability_id"]),
                dict(arguments.get("arguments") or {}),
                context=context,
            )
        )
        ok = bool(payload.get("ok"))
        map_session = payload.get("map_session")
        map_session_payload = (
            map_session.model_dump(mode="json")
            if isinstance(map_session, MapSession)
            else map_session
        )
        if is_json_object(map_session_payload):
            # Keep the full validated candidate on the server side.  The
            # model-facing evidence envelope below contains only a bounded
            # identity summary and never re-serializes provider geometry.
            context.metadata["prepared_map_session"] = dict(map_session_payload)
            prepared_sessions = context.metadata.get("prepared_map_sessions")
            if not is_json_array(prepared_sessions):
                prepared_sessions = []
                context.metadata["prepared_map_sessions"] = prepared_sessions
            # Keep each successful candidate.  A provider may reuse a
            # session identifier for separate layers, and the shared map
            # assembler deduplicates stable overlay instances when needed.
            prepared_sessions.append(dict(map_session_payload))
        status = "available" if ok else "failed"
        if ok and payload.get("direct_result") in (None, [], {}, "") and map_session is None:
            status = "valid_empty"
        evidence_payload = {**payload, "map_session": map_session_payload}
        evidence_ref = self._persist_evidence(
            context=context,
            kind="capability_result",
            media_type="application/json",
            status=status,
            payload=evidence_payload,
            summary={
                "operation": payload.get("operation"),
                "capability_id": arguments.get("capability_id"),
                "map_eligibility": "renderable" if map_session is not None else "unknown",
                **(
                    {"map_session": self._map_session_summary(map_session_payload)}
                    if is_json_object(map_session_payload)
                    else {}
                ),
            },
            provenance={
                "capability_id": arguments.get("capability_id"),
                "target_id": context.metadata.get("target_id"),
            },
        )
        if str(context.metadata.get("execution_mode") or "native") == "deterministic":
            payload["evidence_ref"] = evidence_ref
            return payload
        envelope = AgentEvidenceEnvelope(
            ok=ok,
            status=status,
            evidence_ref=evidence_ref,
            summary={
                "operation": payload.get("operation"),
                "capability_id": arguments.get("capability_id"),
                "map_session": self._map_session_summary(map_session_payload)
                if is_json_object(map_session_payload)
                else None,
            },
            provenance={"capability_id": arguments.get("capability_id")},
            map_eligibility="renderable" if map_session is not None else "unknown",
            error=(
                cast(dict[str, Any], payload.get("error"))
                if is_json_object(payload.get("error"))
                else None
            ),
            state_changes=[
                {"type": "evidence_available", "evidence_ref": evidence_ref}
                if evidence_ref
                else {}
            ],
        ).model_dump(mode="json")
        # Native planned-result validation needs the application-owned
        # capability/target identity and the validated map candidate at the
        # envelope boundary.  Keep the evidence envelope shape intact while
        # carrying these typed execution fields alongside its compact summary.
        envelope.update(
            {
                "capability_id": arguments.get("capability_id"),
                "target_id": context.metadata.get("target_id"),
                "result_status": status,
            }
        )
        return envelope

    # -------------------------------------------------------------------------
    async def _provider_layers_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        response = await self.geospatial_api_service.list_provider_layers(
            str(arguments["provider_id"]),
            query=arguments.get("query")
            if isinstance(arguments.get("query"), str)
            else None,
            limit=int(arguments.get("limit") or 50),
            refresh=bool(arguments.get("refresh", False)),
        )
        payload = response.model_dump(mode="json")
        evidence_ref = self._persist_evidence(
            context=context,
            kind="provider_layer_descriptor",
            media_type="application/json",
            status="valid_empty" if not payload.get("layers") else "available",
            payload=payload,
            summary={
                "provider_id": arguments.get("provider_id"),
                "layer_count": len(payload.get("layers") or []),
                "map_eligibility": "renderable" if payload.get("layers") else "not_renderable",
            },
            provenance={"provider_id": arguments.get("provider_id")},
        )
        if str(context.metadata.get("execution_mode") or "native") == "deterministic":
            payload["evidence_ref"] = evidence_ref
            return payload
        return AgentEvidenceEnvelope(
            ok=True,
            status="valid_empty" if not payload.get("layers") else "available",
            evidence_ref=evidence_ref,
            summary={
                "provider_id": arguments.get("provider_id"),
                "layer_count": len(payload.get("layers") or []),
            },
            provenance={"provider_id": arguments.get("provider_id")},
            map_eligibility="renderable" if payload.get("layers") else "not_renderable",
            pagination={"next_cursor": payload.get("next_cursor")},
        ).model_dump(mode="json")

    # -------------------------------------------------------------------------
    async def _inspect_evidence_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        if self.evidence_repository is None:
            return AgentEvidenceEnvelope(
                ok=False,
                status="error",
                error={"code": "evidence_unavailable", "message": "Evidence storage is not configured."},
            ).model_dump(mode="json")
        evidence_id = str(arguments.get("evidence_ref") or "")
        item = self.evidence_repository.get_payload(
            evidence_id,
            conversation_id=context.conversation_id,
        )
        if item is None or context.conversation_id is None:
            return AgentEvidenceEnvelope(
                ok=False,
                status="error",
                error={"code": "unknown_evidence", "message": "Evidence reference is unavailable."},
            ).model_dump(mode="json")
        summary, raw = item
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"byte_size": len(raw), "media_type": summary.media_type}
        view = str(arguments.get("view") or "metadata")
        result = self._inspect_payload(
            payload,
            view=view,
            fields=[
                str(value)
                for value in cast(list[Any], arguments.get("fields") or [])
            ],
            cursor=arguments.get("cursor"),
            limit=int(arguments.get("limit") or 100),
        )
        return AgentEvidenceEnvelope(
            ok=True,
            status=summary.status,
            evidence_ref=evidence_id,
            summary={"view": view, "result": result, "source": summary.summary},
            provenance=summary.provenance,
            map_eligibility=summary.map_eligibility,
            pagination=result.get("pagination") if is_json_object(result) else None,
        ).model_dump(mode="json")

    # -------------------------------------------------------------------------
    async def _transform_evidence_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        if self.evidence_repository is None or context.conversation_id is None:
            return AgentEvidenceEnvelope(
                ok=False,
                status="error",
                error={"code": "evidence_unavailable", "message": "Evidence storage is not configured."},
            ).model_dump(mode="json")
        refs = [
            str(value)
            for value in cast(list[Any], arguments.get("evidence_refs") or [])
        ]
        raw_operations = arguments.get("operations")
        operations: list[Any] = (
            raw_operations if is_json_array(raw_operations) else []
        )
        if len(operations) > 8 or not refs:
            return AgentEvidenceEnvelope(
                ok=False,
                status="error",
                error={"code": "invalid_transform", "message": "At least one evidence reference and at most eight operations are required."},
            ).model_dump(mode="json")
        records: list[Any] = []
        parents: list[str] = []
        for ref in refs:
            item = self.evidence_repository.get_payload(
                ref,
                conversation_id=context.conversation_id,
            )
            if item is None:
                return AgentEvidenceEnvelope(
                    ok=False,
                    status="error",
                    error={"code": "unknown_evidence", "message": f"Evidence '{ref}' is unavailable."},
                ).model_dump(mode="json")
            summary, raw = item
            parents.append(summary.evidence_id)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return AgentEvidenceEnvelope(
                    ok=False,
                    status="error",
                    error={"code": "unsupported_transform", "message": "Only normalized JSON vector or tabular evidence can be transformed."},
                ).model_dump(mode="json")
            records.extend(self._records_from_payload(value))
        transformed, error = self._apply_transform_operations(records, operations)
        if error:
            return AgentEvidenceEnvelope(ok=False, status="error", error={"code": "invalid_transform", "message": error}).model_dump(mode="json")
        evidence_ref = self._persist_evidence(
            context=context,
            kind="derived",
            media_type="application/json",
            status="valid_empty" if not transformed else "available",
            payload={"records": transformed},
            summary={"record_count": len(transformed), "parent_count": len(parents), "map_eligibility": "renderable" if transformed else "not_renderable"},
            provenance={"operation_count": len(operations), "operations": [str(item.get("op") or "") for item in operations if is_json_object(item)]},
            parent_evidence_ids=parents,
        )
        return AgentEvidenceEnvelope(
            ok=True,
            status="valid_empty" if not transformed else "available",
            evidence_ref=evidence_ref,
            summary={"record_count": len(transformed), "parents": parents},
            provenance={"operation_count": len(operations)},
            map_eligibility="renderable" if transformed else "not_renderable",
        ).model_dump(mode="json")

    # -------------------------------------------------------------------------
    async def _prepare_map_tool_handler(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext,
    ) -> dict[str, Any]:
        evidence_refs = [
            str(value)
            for value in cast(list[Any], arguments.get("evidence_refs") or [])
        ]
        location_refs = [
            str(value)
            for value in cast(list[Any], arguments.get("location_refs") or [])
        ]
        if not evidence_refs and not location_refs:
            return AgentEvidenceEnvelope(ok=False, status="error", error={"code": "missing_map_input", "message": "Map preparation requires evidence or location references."}).model_dump(mode="json")
        map_sessions: list[MapSession] = []
        if self.evidence_repository is not None:
            for ref in evidence_refs:
                item = self.evidence_repository.get_payload(
                    ref,
                    conversation_id=context.conversation_id,
                )
                if item is None:
                    continue
                _summary, raw = item
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                candidate = payload.get("map_session") if is_json_object(payload) else None
                if is_json_object(candidate):
                    try:
                        map_sessions.append(MapSession.model_validate(candidate))
                    except Exception:
                        continue
        map_session = self._merge_map_sessions(map_sessions)
        layer_options = arguments.get("layer_options")
        if map_session is None and is_json_object(layer_options):
            provider_id = str(layer_options.get("provider_id") or "").strip()
            layer_id = str(layer_options.get("layer_id") or "").strip()
            if provider_id and layer_id:
                rendered = await self._prepare_provider_layer(
                    {
                        "provider_id": provider_id,
                        "layer_id": layer_id,
                        "target_id": location_refs[0] if len(location_refs) == 1 else None,
                        "time": layer_options.get("time"),
                        "style": layer_options.get("style"),
                        "format": layer_options.get("format"),
                    },
                    context,
                )
                rendered_map = rendered.get("map_session")
                if rendered.get("ok") and is_json_object(rendered_map):
                    try:
                        map_session = MapSession.model_validate(rendered_map)
                    except Exception:
                        map_session = None
        if map_session is None:
            return AgentEvidenceEnvelope(
                ok=False,
                status="error",
                error={"code": "map_not_preparable", "message": "No renderable map session or provider layer descriptor is available from the supplied evidence."},
                state_changes=[{"type": "map_preparation_failed"}],
            ).model_dump(mode="json")
        map_evidence_ref = self._persist_evidence(
            context=context,
            kind="provider_layer_descriptor",
            media_type="application/vnd.aegis.map-session+json",
            status="available",
            payload={"map_session": map_session.model_dump(mode="json")},
            summary={
                "operation": "map_session_created",
                "overlay_count": len(map_session.overlay_collection.instances),
                "map_eligibility": "renderable",
            },
            provenance={
                "source_evidence_refs": evidence_refs,
                "location_refs": location_refs,
                "viewport_strategy": arguments.get("viewport_strategy")
                or "fit_results",
            },
            parent_evidence_ids=evidence_refs,
        )
        context.metadata["prepared_map_session"] = map_session.model_dump(mode="json")
        all_evidence_refs = list(
            dict.fromkeys([*evidence_refs, *( [map_evidence_ref] if map_evidence_ref else [] )])
        )
        return {
            "ok": True,
            "status": "available",
            "evidence_ref": map_evidence_ref or (evidence_refs[0] if evidence_refs else None),
            "summary": {
                "operation": "map_session_created",
                "required_overlay_ids": [
                    instance.instance_id
                    for instance in map_session.overlay_collection.instances
                ],
                "map_session": self._map_session_summary(map_session),
                "evidence_refs": all_evidence_refs,
                "location_refs": location_refs,
                "map_eligibility": "renderable",
            },
            "provenance": {"viewport_strategy": arguments.get("viewport_strategy") or "fit_results"},
            "map_eligibility": "renderable",
            "state_changes": [{"type": "map_prepared", "render_status": "awaiting_render"}],
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _merge_map_sessions(sessions: list[MapSession]) -> MapSession | None:
        """Combine every validated evidence map into one renderable session."""

        if not sessions:
            return None
        candidate = sessions[-1].model_copy(deep=True)
        instances: list[OverlayInstance] = []
        warnings: list[str] = []
        for session in sessions:
            instances.extend(
                item.model_copy(deep=True)
                for item in session.overlay_collection.instances
            )
            warnings.extend(session.compliance_warnings)
        collection = OverlayCollectionService.merge_instances(
            OverlayCollectionState(), instances
        )
        return candidate.model_copy(
            update={
                "overlay_collection": collection,
                "compliance_warnings": list(dict.fromkeys(warnings)),
            },
            deep=True,
        )

    # -------------------------------------------------------------------------
    def _persist_evidence(
        self,
        *,
        context: AgentExecutionContext,
        kind: str,
        media_type: str,
        status: Any,
        payload: Any,
        summary: dict[str, Any],
        provenance: dict[str, Any],
        parent_evidence_ids: list[str] | None = None,
    ) -> str | None:
        if self.evidence_repository is None or context.conversation_id is None:
            return None
        record = self.evidence_repository.create(
            conversation_id=context.conversation_id,
            run_id=context.request_id,
            kind=kind,
            media_type=media_type,
            status=status,
            payload=payload,
            summary=summary,
            provenance=provenance,
            parent_evidence_ids=parent_evidence_ids,
        )
        return record.evidence_id

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_session_summary(
        map_session: MapSession | dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return a bounded identity summary without provider feature payloads."""

        if isinstance(map_session, MapSession):
            session = map_session
        elif is_json_object(map_session):
            try:
                session = MapSession.model_validate(map_session)
            except Exception:  # noqa: BLE001
                return {"map_session_available": False}
        else:
            return {"map_session_available": False}
        instances = session.overlay_collection.instances
        return {
            "session_id": session.session_id,
            "basemap_id": session.basemap_id,
            "bounds": session.bounds,
            "viewport": session.viewport.model_dump(mode="json"),
            "overlay_collection": {
                "collection_id": session.overlay_collection.collection_id,
                "revision": session.overlay_collection.revision,
                "instance_ids": [item.instance_id for item in instances],
                "instances": [
                    {
                        "instance_id": item.instance_id,
                        "capability_id": item.capability_id,
                        "label": item.label,
                        "provider": item.provider,
                        "overlay_type": item.overlay_type,
                        "rendering_mode": item.rendering_mode,
                        "visible": item.visible,
                        "render_variant": item.render_variant,
                    }
                    for item in instances
                ],
            },
            "compliance_warning_count": len(session.compliance_warnings),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
        if is_json_object(payload):
            for key in ("records", "features", "items", "data"):
                value = payload.get(key)
                if is_json_array(value):
                    return [item for item in value if is_json_object(item)]
            return [payload]
        return [item for item in payload if is_json_object(item)] if is_json_array(payload) else []

    @staticmethod
    def _inspect_payload(payload: Any, *, view: str, fields: list[str], cursor: Any, limit: int) -> dict[str, Any]:
        if view == "metadata":
            return {"type": type(payload).__name__, "keys": list(payload)[:100] if is_json_object(payload) else [], "record_count": len(AgentToolCatalogService._records_from_payload(payload))}
        records = AgentToolCatalogService._records_from_payload(payload)
        if fields:
            records = [{key: item.get(key) for key in fields if key in item} for item in records]
        if view == "schema":
            keys = sorted({key for item in records for key in item})
            return {"fields": keys, "record_count": len(records)}
        if view == "statistics":
            stats: dict[str, Any] = {}
            for key in sorted({key for item in records for key in item}):
                values: list[float] = []
                for item in records:
                    value = item.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        values.append(float(value))
                if values:
                    stats[key] = {"min": min(values), "max": max(values), "count": len(values)}
            return {"statistics": stats, "record_count": len(records)}
        start = int(cursor or 0) if str(cursor or "0").isdigit() else 0
        page = records[start : start + max(1, min(limit, 100))]
        return {"records": page, "pagination": {"cursor": str(start + len(page)) if start + len(page) < len(records) else None, "total": len(records)}}

    @staticmethod
    def _apply_transform_operations(records: list[dict[str, Any]], operations: list[Any]) -> tuple[list[dict[str, Any]], str | None]:
        allowed = {"attribute_filter", "temporal_filter", "spatial_filter", "sort", "limit", "field_projection", "aggregate"}
        result = list(records)
        for operation in operations:
            if not is_json_object(operation) or str(operation.get("op") or "") not in allowed:
                return result, "Only the supported declarative geospatial operations are allowed."
            op = str(operation.get("op"))
            if op == "attribute_filter":
                field = str(operation.get("field") or "")
                if not field:
                    return result, f"{op} requires a field."
                expected = operation.get("value")
                operator = str(operation.get("operator") or "eq")
                if operator not in {"eq", "neq", "in", "contains", "gte", "lte"}:
                    return result, "attribute_filter uses an unsupported operator."
                def matches(item: dict[str, Any]) -> bool:
                    actual = item.get(field)
                    if operator == "eq":
                        return actual == expected
                    if operator == "neq":
                        return actual != expected
                    if operator == "in":
                        return is_json_array(expected) and actual in expected
                    if operator == "contains":
                        if isinstance(actual, str) and isinstance(expected, str):
                            return expected in actual
                        return is_json_array(actual) and expected in actual
                    if operator == "gte":
                        return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual >= expected
                    return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual <= expected
                result = [item for item in result if matches(item)]
            elif op == "temporal_filter":
                field = str(operation.get("field") or "timestamp")
                start = str(operation.get("start") or "")
                end = str(operation.get("end") or "")
                if not start and not end:
                    return result, "temporal_filter requires a start or end bound."
                def in_time_window(item: dict[str, Any]) -> bool:
                    actual = item.get(field)
                    return (
                        isinstance(actual, str)
                        and (not start or actual >= start)
                        and (not end or actual <= end)
                    )

                result = [item for item in result if in_time_window(item)]
            elif op == "spatial_filter":
                field = str(operation.get("field") or "geometry")
                center = operation.get("center")
                radius_km = operation.get("radius_km")
                if not is_json_array(center) or len(center) != 2 or not isinstance(radius_km, (int, float)) or radius_km <= 0:
                    return result, "spatial_filter requires center [longitude, latitude] and positive radius_km."
                try:
                    lon0, lat0 = float(center[0]), float(center[1])
                    radius_value = float(radius_km)
                except (TypeError, ValueError):
                    return result, "spatial_filter requires numeric center and radius."
                def within(item: dict[str, Any]) -> bool:
                    geometry = item.get(field)
                    coordinates = geometry.get("coordinates") if is_json_object(geometry) else geometry
                    if not is_json_array(coordinates) or len(coordinates) < 2:
                        return False
                    try:
                        lon, lat = float(coordinates[0]), float(coordinates[1])
                    except (TypeError, ValueError):
                        return False
                    dlat = math.radians(lat - lat0)
                    dlon = math.radians(lon - lon0)
                    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat0)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
                    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a))) <= radius_value
                result = [item for item in result if within(item)]
            elif op == "sort":
                field = str(operation.get("field") or "")
                if not field:
                    return result, "sort requires a field."
                result.sort(key=lambda item: (item.get(field) is None, str(item.get(field) or "")), reverse=bool(operation.get("descending")))
            elif op == "limit":
                count = operation.get("value")
                if not isinstance(count, int) or count < 1 or count > 10000:
                    return result, "limit must be an integer between 1 and 10000."
                result = result[:count]
            elif op == "field_projection":
                fields = operation.get("fields")
                if not is_json_array(fields) or not fields:
                    return result, "field_projection requires a non-empty fields list."
                result = [{str(key): item.get(str(key)) for key in fields if str(key) in item} for item in result]
            elif op == "aggregate":
                field = str(operation.get("field") or "")
                group_by = str(operation.get("group_by") or "")
                if not field or not group_by:
                    return result, "aggregate requires field and group_by."
                groups: dict[str, list[float]] = {}
                for item in result:
                    value = item.get(field)
                    group = str(item.get(group_by) or "")
                    if isinstance(value, (int, float)):
                        groups.setdefault(group, []).append(float(value))
                result = [{group_by: group, field: sum(values), "count": len(values)} for group, values in groups.items()]
        return result, None

    # -------------------------------------------------------------------------
    async def _prepare_provider_layer(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> GeospatialCapabilityExecutionResult:
        provider_id = str(arguments["provider_id"])
        layer_id = str(arguments["layer_id"])
        capability_id = f"{provider_id}:{layer_id}"
        if self.search_orchestrator is None:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="provider_error",
                code="provider_error",
                message="Search orchestrator is not configured for provider layer rendering.",
            )
        resolved_location = await self._resolve_location(arguments, context)
        if is_json_object(resolved_location) and resolved_location.get("error"):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        if not isinstance(resolved_location, ResolvedLocation):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        parsed_request = self._parsed_turn(context)
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=(
                parsed_request.normalized_action.action_id
                if parsed_request is not None
                else "provider_layer_render"
            ),
            basemap_id=parsed_request.requested_basemap
            if parsed_request is not None
            else None,
            overlay_ids=[],
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=parsed_request,
            canonical_request=(
                context.canonical_request if context is not None else None
            ),
            target_id=(
                str(context.metadata.get("target_id") or "").strip()
                if context is not None
                else None
            ),
            canonical_arguments=arguments,
            active_visualization=(
                context.map_state.get("active_visualization")
                if context is not None and is_json_object(context.map_state)
                else None
            ),
            provider_layer_selections=[
                ProviderLayerSelection(
                    provider_id=provider_id,
                    layer_id=layer_id,
                    time=arguments.get("time")
                    if isinstance(arguments.get("time"), str)
                    else None,
                    style=arguments.get("style")
                    if isinstance(arguments.get("style"), str)
                    else None,
                    format=arguments.get("format")
                    if isinstance(arguments.get("format"), str)
                    else None,
                )
            ],
        )
        map_session = await self.search_orchestrator.execute(request)
        provider_failure = next(
            (
                warning
                for warning in map_session.compliance_warnings
                if warning.startswith(f"Provider layer '{capability_id}' failed (")
            ),
            None,
        )
        if provider_failure:
            supported_codes = {
                "auth_required",
                "rate_limited",
                "provider_unavailable",
                "invalid_query",
                "malformed_response",
                "unsupported",
            }
            code = provider_failure.split(" failed (", 1)[1].split("):", 1)[0]
            if code not in supported_codes:
                code = "provider_unavailable"
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="provider_error",
                code=code,
                message=provider_failure.rstrip("."),
            )
        return self._map_result(
            capability_id=capability_id,
            arguments=arguments,
            map_session=map_session,
        )

    # -------------------------------------------------------------------------
    def list_geospatial_capabilities(
        self,
        filters: CapabilityCatalogFilter,
    ) -> dict[str, Any]:
        items = self._all_capabilities()
        query = str(filters.query or "").strip().casefold()
        category = str(filters.category or "").strip().casefold()
        geometry_type = str(filters.geometry_type or "").strip().casefold()
        capability_domain = str(filters.capability_domain or "").strip().casefold()
        temporal_support = str(filters.temporal_support or "").strip().casefold()
        analysis_operation = str(filters.analysis_operation or "").strip().casefold()
        if query:
            items = [
                item
                for item in items
                if query
                in " ".join(
                    [
                        str(item.get("id") or ""),
                        str(item.get("name") or ""),
                        str(item.get("description") or ""),
                    ]
                ).casefold()
            ]
        if category:
            items = [
                item
                for item in items
                if category
                in {
                    str(item.get("type") or "").casefold(),
                    str(item.get("capabilityKind") or "").casefold(),
                }
            ]
        if geometry_type:
            items = [
                item
                for item in items
                if geometry_type
                == str(
                    json_object(item.get("metadata")).get("geometry_type") or ""
                ).casefold()
            ]
        if capability_domain:
            items = [
                item
                for item in items
                if capability_domain
                == str(
                    item.get("capabilityDomain")
                    or json_object(item.get("metadata")).get("capability_domain")
                    or ""
                ).casefold()
            ]
        if temporal_support:
            items = [
                item
                for item in items
                if temporal_support
                == str(
                    item.get("temporalSupport")
                    or json_object(item.get("metadata")).get("temporal_support")
                    or ""
                ).casefold()
            ]
        if analysis_operation:
            items = [
                item
                for item in items
                if analysis_operation
                in {
                    str(item.get("analysisOperation") or "").casefold(),
                    str(json_object(item.get("metadata")).get("analysis_operation") or "").casefold(),
                }
            ]
        if filters.renderable is not None:
            items = [
                item
                for item in items
                if bool(
                    item.get("renderable")
                    if item.get("renderable") is not None
                    else json_object(item.get("metadata")).get("renderable")
                )
                is filters.renderable
            ]
        items = sorted(items, key=lambda item: str(item.get("id") or ""))
        offset = self._decode_cursor(filters.cursor)
        limit = max(1, min(filters.limit or CATALOG_PAGE_LIMIT, CATALOG_PAGE_LIMIT))
        page_items = items[offset : offset + limit]
        next_offset = offset + len(page_items)
        return {
            "items": [self._compact_descriptor(item) for item in page_items],
            "next_cursor": str(next_offset) if next_offset < len(items) else None,
            "limit": limit,
            "total": len(items),
        }

    # -------------------------------------------------------------------------
    def describe_geospatial_capability(self, capability_id: str) -> dict[str, Any]:
        capability = self.capability_registry.get_capability(capability_id)
        if capability is None:
            raise ValueError(f"Unknown geospatial capability '{capability_id}'.")
        return {
            "capability_id": capability_id,
            "manifest": capability,
            "argument_schema": self._require_argument_schema(capability),
        }

    # -------------------------------------------------------------------------
    async def execute_geospatial_capability(
        self,
        capability_id: str,
        arguments: dict[str, Any],
        *,
        context: AgentExecutionContext | None = None,
    ) -> GeospatialCapabilityExecutionResult:
        try:
            descriptor = self.describe_geospatial_capability(capability_id)
        except CapabilityArgumentSchemaError as exc:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="invalid_arguments",
                code="missing_argument_schema",
                message=str(exc),
            )
        validation_error = ToolRegistry._validate_arguments(  # pyright: ignore[reportPrivateUsage]
            descriptor["argument_schema"],
            arguments,
        )
        if validation_error is not None:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="invalid_arguments",
                code="invalid_arguments",
                message=validation_error,
            )

        scope_error = self._canonical_scope_error(context, arguments)
        if scope_error is not None:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="invalid_arguments",
                code="missing_analysis_geometry",
                message=scope_error,
            )

        manifest = descriptor["manifest"]
        parsed_request = self._parsed_request_from_context(context)
        if self.policy_engine is not None and parsed_request is not None:
            authorization = self.policy_engine.authorize_capability_execution(
                capability_id,
                arguments,
                parsed_request,
                context or AgentExecutionContext(),
            )
            if not authorization.allowed:
                return self._authorization_error_result(
                    capability_id=capability_id,
                    arguments=arguments,
                    authorization=authorization,
                )

        if self._is_basemap_capability(manifest):
            if self.search_orchestrator is not None:
                resolved_location = await self._resolve_location(arguments, context)
                if not (
                    is_json_object(resolved_location) and resolved_location.get("error")
                ):
                    if not isinstance(resolved_location, ResolvedLocation):
                        return cast(
                            GeospatialCapabilityExecutionResult, resolved_location
                        )
                    plan = self._build_map_execution_plan(
                        capability_id=capability_id,
                        manifest=manifest,
                        context=context,
                    )
                    request = self.request_builder.build_location_search_request(
                        plan,
                        resolved_location,
                        turn_contract=self._parsed_turn(context),
                        canonical_request=(
                            context.canonical_request if context is not None else None
                        ),
                        target_id=(
                            str(context.metadata.get("target_id") or "").strip()
                            if context is not None
                            else None
                        ),
                        canonical_arguments=arguments,
                        active_visualization=(
                            context.map_state.get("active_visualization")
                            if context is not None and is_json_object(context.map_state)
                            else None
                        ),
                    )
                    map_session = await self.search_orchestrator.execute(request)
                    return self._map_result(
                        capability_id=capability_id,
                        arguments=arguments,
                        map_session=map_session,
                    )
            return self._capability_selection_result(
                capability_id=capability_id,
                arguments=arguments,
                selection={"basemap_id": capability_id, "overlay_ids": []},
            )

        if self._supports_direct_execution(capability_id, manifest):
            direct_result = await self._execute_direct_result(
                capability_id=capability_id,
                arguments=arguments,
                context=context,
            )
            if direct_result.get("ok") is False:
                return direct_result
            return direct_result

        if self._supports_map_execution(capability_id, manifest):
            if self.search_orchestrator is None:
                return self._error_result(
                    capability_id=capability_id,
                    arguments=arguments,
                    operation="provider_error",
                    code="provider_error",
                    message="Search orchestrator is not configured for map execution.",
                )
            resolved_location = await self._resolve_location(arguments, context)
            if is_json_object(resolved_location) and resolved_location.get("error"):
                return cast(GeospatialCapabilityExecutionResult, resolved_location)
            if not isinstance(resolved_location, ResolvedLocation):
                return cast(GeospatialCapabilityExecutionResult, resolved_location)
            plan = self._build_map_execution_plan(
                capability_id=capability_id, manifest=manifest, context=context
            )
            request = self.request_builder.build_location_search_request(
                plan,
                resolved_location,
                turn_contract=self._parsed_turn(context),
                canonical_request=(
                    context.canonical_request if context is not None else None
                ),
                target_id=(
                    str(context.metadata.get("target_id") or "").strip()
                    if context is not None
                    else None
                ),
                canonical_arguments=arguments,
                active_visualization=(
                    context.map_state.get("active_visualization")
                    if context is not None and is_json_object(context.map_state)
                    else None
                ),
            )
            map_session = await self.search_orchestrator.execute(request)
            return self._map_result(
                capability_id=capability_id,
                arguments=arguments,
                map_session=map_session,
            )

        return {
            "capability_id": capability_id,
            "arguments": arguments,
            "ok": True,
            "operation": "validated_only",
            "map_session": None,
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {"manifest": self._compact_descriptor(manifest)},
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _canonical_scope_error(
        context: AgentExecutionContext | None,
        arguments: dict[str, Any] | None = None,
    ) -> str | None:
        if context is None or context.canonical_request is None:
            return None
        arguments = arguments or {}
        location_refs = arguments.get("location_refs")
        target_id = str(
            context.metadata.get("target_id")
            or arguments.get("target_id")
            or arguments.get("location_ref")
            or (
                location_refs[0]
                if is_json_array(location_refs) and len(location_refs) == 1
                else ""
            )
            or ""
        ).strip()
        target = (
            context.canonical_request.target(target_id)
            if target_id
            else context.canonical_request.primary_target
        )
        constraint = next(
            (
                item
                for item in context.canonical_request.spatial_constraints
                if target is not None and item.target_id == target.target_id
            ),
            None,
        )
        if (
            constraint is not None
            and constraint.analysis_scope in {"administrative_geometry", "feature_geometry"}
            and (target is None or not target.geometry_ref)
        ):
            return (
                "The requested geographic scope requires a verified analysis "
                "geometry; a geocoder point or viewport bbox is insufficient."
            )
        return None

    # -------------------------------------------------------------------------
    def _all_capabilities(self) -> list[dict[str, Any]]:
        snapshot = self.capability_registry.snapshot
        return [
            *snapshot.basemaps,
            *snapshot.overlays,
            *snapshot.cameras,
            *snapshot.transit,
            *snapshot.tools,
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _compact_descriptor(item: dict[str, Any]) -> dict[str, Any]:
        metadata = json_object(item.get("metadata"))
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "description": item.get("description"),
            "provider": item.get("provider"),
            "category": item.get("capabilityKind") or item.get("type"),
            "geometry_type": metadata.get("geometry_type"),
            "capability_domain": item.get("capabilityDomain") or metadata.get("capability_domain"),
            "temporal_support": item.get("temporalSupport") or metadata.get("temporal_support"),
            "analysis_operation": item.get("analysisOperation") or metadata.get("analysis_operation"),
            "renderable": item.get("renderable") if item.get("renderable") is not None else metadata.get("renderable"),
            "queryable": metadata.get("queryable"),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _require_argument_schema(capability: dict[str, Any]) -> dict[str, Any]:
        metadata = json_object(capability.get("metadata"))
        schema = metadata.get("parameters_json_schema") or metadata.get(
            "argument_schema"
        )
        if is_json_object(schema):
            return schema
        capability_id = str(capability.get("id") or "unknown")
        raise CapabilityArgumentSchemaError(
            f"Capability '{capability_id}' does not declare an executable argument schema."
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            return max(0, int(cursor))
        except ValueError:
            return 0

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_basemap_capability(manifest: dict[str, Any]) -> bool:
        return (
            str(manifest.get("capabilityKind") or manifest.get("type") or "")
            .strip()
            .lower()
            == "basemap"
        )

    # -------------------------------------------------------------------------
    def _supports_direct_execution(
        self, capability_id: str, manifest: dict[str, Any]
    ) -> bool:
        if self.tool_registry is None:
            return False
        return (
            self.runtime_registry.supports_mode(capability_id, "direct_text")
            and self.tool_registry.get_handler(capability_id) is not None
        )

    # -------------------------------------------------------------------------
    def _supports_map_execution(
        self, capability_id: str, manifest: dict[str, Any]
    ) -> bool:
        if self._is_basemap_capability(manifest):
            return False
        return self.runtime_registry.supports_mode(capability_id, "map")

    # -------------------------------------------------------------------------
    @staticmethod
    def _authorization_error_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        authorization: ToolAuthorizationResult,
    ) -> GeospatialCapabilityExecutionResult:
        metadata = dict(authorization.metadata or {})
        code = str(metadata.get("code") or "unsupported_capability")
        operation_by_code = {
            "missing_credentials": "missing_credentials",
            "missing_access": "missing_access",
            "unavailable_coverage": "unavailable",
            "invalid_arguments": "invalid_arguments",
            "tool_rejected": "provider_error",
            "unsupported_capability": "unsupported_capability",
        }
        operation = operation_by_code.get(code, "unsupported_capability")
        warnings = (
            [authorization.reason]
            if code in {"missing_credentials", "missing_access"}
            and authorization.reason
            else []
        )
        return {
            "ok": False,
            "operation": operation,
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": warnings,
            "error": {
                "code": code,
                "message": authorization.reason or "Capability execution rejected.",
            },
            "metadata": metadata,
        }

    # -------------------------------------------------------------------------
    async def _execute_direct_result(
        self,
        *,
        capability_id: str,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> GeospatialCapabilityExecutionResult:
        if self.tool_registry is None:
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="provider_error",
                code="provider_error",
                message="Tool registry is not configured for direct execution.",
            )
        resolved_location = await self._resolve_location(arguments, context)
        if is_json_object(resolved_location) and resolved_location.get("error"):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        if not isinstance(resolved_location, ResolvedLocation):
            return cast(GeospatialCapabilityExecutionResult, resolved_location)
        plan = self._build_direct_execution_plan(
            capability_id=capability_id, arguments=arguments, context=context
        )
        direct_result = await self.tool_registry.execute(
            capability_id, plan, resolved_location
        )
        if is_json_object(direct_result) and direct_result.get("error"):
            return self._error_result(
                capability_id=capability_id,
                arguments=arguments,
                operation="provider_error",
                code="provider_error",
                message=str(direct_result["error"]),
            )
        return {
            "ok": True,
            "operation": "direct_result_created",
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": direct_result,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {},
        }

    # -------------------------------------------------------------------------
    async def _resolve_location(
        self,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> ResolvedLocation | GeospatialCapabilityExecutionResult:
        if context is not None and context.canonical_request is not None:
            raw_location_refs = arguments.get("location_refs")
            location_refs = raw_location_refs if is_json_array(raw_location_refs) else []
            target_id = str(
                context.metadata.get("target_id")
                or arguments.get("target_id")
                or arguments.get("location_ref")
                or (
                    location_refs[0]
                    if len(location_refs) == 1
                    else ""
                )
                or ""
            ).strip()
            if target_id:
                target = context.canonical_request.target(target_id)
                if target is None:
                    return self._error_result(
                        capability_id="location_resolution",
                        arguments=arguments,
                        operation="invalid_arguments",
                        code="unknown_target",
                        message="The planned geographic target is not in the canonical request.",
                    )
                if target.resolved_location is None:
                    return self._error_result(
                        capability_id="location_resolution",
                        arguments=arguments,
                        operation="invalid_arguments",
                        code="unresolved_target",
                        message="The planned geographic target has not been resolved.",
                    )
                # Planned target identity is authoritative. The provider
                # arguments remain a transport shape and cannot select a
                # different place through a second geocoding pass.
                return target.resolved_location
            canonical_targets = [
                target
                for target in context.canonical_request.targets
                if target.resolved_location is not None
            ]
            primary = context.canonical_request.primary_target
            if primary is None or primary.resolved_location is None:
                return self._error_result(
                    capability_id="location_resolution",
                    arguments=arguments,
                    operation="invalid_arguments",
                    code="unresolved_target",
                    message="The canonical request has no resolved geographic target.",
                )
            argument_target = self._match_canonical_argument_target(
                arguments, canonical_targets
            )
            has_location_argument = self._has_location_argument(arguments)
            if argument_target is not None:
                return argument_target.resolved_location  # type: ignore[return-value]
            if has_location_argument:
                code = (
                    "canonical_target_required"
                    if len(canonical_targets) > 1
                    else "canonical_location_mismatch"
                )
                return self._error_result(
                    capability_id="location_resolution",
                    arguments=arguments,
                    operation="invalid_arguments",
                    code=code,
                    message=(
                        "The tool arguments do not identify one of the canonical "
                        "geographic targets."
                    ),
                )
            # A planned/native call with no location fields uses the canonical
            # primary target. Provider arguments never trigger a second lookup.
            return primary.resolved_location
        if context is not None and context.resolved_location is not None:
            # A run has one location owner.  Tool arguments are execution
            # parameters, not a second parser or geocoder input.
            return context.resolved_location
        parsed_request = self._parsed_request_from_context(context)
        argument_signals = self._build_argument_location_signals(
            arguments,
            allow_untyped_city=context is None or parsed_request is None,
        )
        parsed_signals = (
            parsed_request.location_signals if parsed_request is not None else []
        )
        memory_snapshot = context.map_state if context is not None else {}
        resolved = await self.location_resolver.resolve_location_signals(
            [*argument_signals, *parsed_signals],
            json_object(memory_snapshot),
        )
        if isinstance(resolved, ClarificationRequest):
            return self._error_result(
                capability_id="location_resolution",
                arguments=arguments,
                operation="invalid_arguments",
                code="missing_location",
                message=resolved.question,
            )
        return resolved

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_location_argument(arguments: dict[str, Any]) -> bool:
        return any(
            key in arguments
            and arguments.get(key) is not None
            and str(arguments.get(key)).strip()
            for key in ("location", "address", "city", "country")
        ) or (
            isinstance(arguments.get("latitude"), (int, float))
            and isinstance(arguments.get("longitude"), (int, float))
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _match_canonical_argument_target(
        arguments: dict[str, Any],
        targets: list[Any],
    ) -> Any | None:
        latitude = arguments.get("latitude")
        longitude = arguments.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            matches = [
                target
                for target in targets
                if target.resolved_location is not None
                and abs(float(target.resolved_location.latitude) - float(latitude)) <= 1e-3
                and abs(float(target.resolved_location.longitude) - float(longitude)) <= 1e-3
            ]
            if len(matches) == 1:
                return matches[0]
            return None
        raw = next(
            (
                str(arguments.get(key) or "").strip()
                for key in ("location", "address", "city", "country")
                if str(arguments.get(key) or "").strip()
            ),
        )
        if not raw:
            return None
        normalized = normalize_target_key(raw)
        matches: list[Any] = []
        for target in targets:
            location = target.resolved_location
            labels = {
                normalize_target_key(target.original_text),
                normalize_target_key(location.label if location is not None else ""),
            }
            if normalized in labels or any(
                value and (value in normalized or normalized in value)
                for value in labels
            ):
                matches.append(target)
        return matches[0] if len(matches) == 1 else None

    # -------------------------------------------------------------------------
    def _build_map_execution_plan(
        self,
        *,
        capability_id: str,
        manifest: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> ExecutionPlan:
        parsed_request = self._parsed_request_from_context(context)
        action_id = (
            parsed_request.normalized_action.action_id
            if parsed_request is not None
            else str(manifest.get("id") or capability_id)
        )
        if self._is_basemap_capability(manifest):
            return ExecutionPlan(
                state="map_search",
                mode="map",
                action_id=action_id,
                basemap_id=capability_id,
            )
        return ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=action_id,
            # A capability fetch still belongs to the current map request.
            # Preserve an explicit basemap intent instead of letting the
            # standalone tool plan silently fall back to the catalog default.
            basemap_id=(
                parsed_request.requested_basemap
                if parsed_request is not None
                else None
            ),
            overlay_ids=[capability_id],
        )

    # -------------------------------------------------------------------------
    def _build_direct_execution_plan(
        self,
        *,
        capability_id: str,
        arguments: dict[str, Any],
        context: AgentExecutionContext | None,
    ) -> ExecutionPlan:
        parsed_request = self._parsed_request_from_context(context)
        action_id = (
            parsed_request.normalized_action.action_id
            if parsed_request is not None
            else capability_id
        )
        temporal_mode = (
            parsed_request.temporal_signal.mode if parsed_request is not None else None
        )
        temporal_text = (
            parsed_request.temporal_signal.raw_text
            if parsed_request is not None
            else None
        )
        temporal_reference_time_iso = (
            parsed_request.temporal_signal.reference_time_iso
            if parsed_request is not None
            else None
        )
        return ExecutionPlan(
            state="direct_tool",
            mode="direct_text",
            action_id=action_id,
            temporal_mode=None if temporal_mode == "none" else temporal_mode,
            temporal_text=temporal_text,
            temporal_reference_time_iso=temporal_reference_time_iso,
            tool_arguments=dict(arguments),
            tool_id=capability_id,
        )

    # -------------------------------------------------------------------------
    def _build_argument_location_signals(
        self,
        arguments: dict[str, Any],
        *,
        allow_untyped_city: bool = True,
    ) -> list[LocationSignal]:
        signals: list[LocationSignal] = []
        location_text = (
            arguments.get("location")
            or arguments.get("location_text")
            or arguments.get("query")
        )
        if isinstance(location_text, str) and location_text.strip():
            requested_type = str(
                arguments.get("location_signal_type")
                or arguments.get("location_type")
                or ""
            ).strip().lower()
            valid_types: set[LocationSignalType] = {
                "address",
                "airport",
                "city",
                "country",
                "poi",
                "feature",
                "landmark",
                "region",
                "river",
                "road",
                "street",
                "station",
                "neighborhood",
                "district",
                "municipality",
                "county",
                "province",
                "state",
            }
            signal_type: LocationSignalType | None = (
                requested_type
                if requested_type in valid_types
                else None
            )
            resolved_signal_type: LocationSignalType = signal_type or "city"
            if signal_type is not None or allow_untyped_city:
                signals.append(
                    LocationSignal(
                        signal_type=resolved_signal_type,
                        raw_value=location_text.strip(),
                        normalized_value=location_text.strip(),
                        confidence=0.9,
                        source="model",
                    )
                )
        latitude = arguments.get("latitude")
        longitude = arguments.get("longitude")
        if isinstance(latitude, int | float) and isinstance(longitude, int | float):
            signals.insert(
                0,
                LocationSignal(
                    signal_type="coordinates",
                    raw_value=f"{latitude},{longitude}",
                    normalized_value=f"{latitude},{longitude}",
                    latitude=float(latitude),
                    longitude=float(longitude),
                    confidence=1.0,
                    source="model",
                ),
            )
        return signals

    # -------------------------------------------------------------------------
    @staticmethod
    def _parsed_turn(context: AgentExecutionContext | None) -> TurnParseResult | None:
        if context is None:
            return None
        try:
            return TurnParseResult.model_validate(context.parsed_request)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _parsed_request_from_context(
        context: AgentExecutionContext | None,
    ) -> TurnParseResult | None:
        if context is None or not is_json_object(context.parsed_request):
            return None
        try:
            return TurnParseResult.model_validate(context.parsed_request)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        map_session: MapSession,
    ) -> GeospatialCapabilityExecutionResult:
        map_payload = json_object(map_session.payload)
        return {
            "ok": True,
            "operation": "map_session_created",
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": map_session.model_dump(mode="json"),
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": list(map_session.compliance_warnings),
            "error": None,
            "metadata": {
                "target_id": map_payload.get("target_id"),
                "analysis_scope": map_payload.get("analysis_scope"),
                "start_time_iso": map_payload.get("start_time_iso"),
                "end_time_iso": map_payload.get("end_time_iso"),
            },
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _capability_selection_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        selection: dict[str, Any],
    ) -> GeospatialCapabilityExecutionResult:
        return {
            "ok": True,
            "operation": "capability_selection_created",
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": None,
            "capability_selection": selection,
            "observations": [],
            "warnings": [],
            "error": None,
            "metadata": {},
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _error_result(
        *,
        capability_id: str,
        arguments: dict[str, Any],
        operation: str,
        code: str,
        message: str,
    ) -> GeospatialCapabilityExecutionResult:
        return {
            "ok": False,
            "operation": operation,
            "capability_id": capability_id,
            "arguments": arguments,
            "map_session": None,
            "direct_result": None,
            "capability_selection": None,
            "observations": [],
            "warnings": [],
            "error": {"code": code, "message": message},
            "metadata": {},
        }
