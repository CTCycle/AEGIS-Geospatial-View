# AEGIS Geospatial View Architecture

Last updated: 2026-04-21
Scope: `AEGIS/` and `tests/`

## 1. System Overview

AEGIS is a chat-first geospatial system with:
- Angular frontend (`AEGIS/client`)
- FastAPI backend (`AEGIS/server`)
- Manifest-driven geospatial capabilities (`AEGIS/resources/manifests`)

The backend executes a deterministic parser -> policy -> execution pipeline.

## 2. Capability Source of Truth

Capabilities are loaded from manifests through `GeospatialManifestLoader` and `CapabilityRegistry`.

Manifest kinds:
- providers
- basemaps
- overlays
- tools
- runtime profiles

Files:
- `AEGIS/resources/manifests/index.json`
- `AEGIS/resources/manifests/runtime_profiles.json`
- `AEGIS/resources/manifests/basemaps/*.json`
- `AEGIS/resources/manifests/overlays/*.json`
- `AEGIS/resources/manifests/tools/*.json`

## 3. Backend Pipeline

Main orchestration entry:
- `AEGIS/server/services/agent/orchestrator.py`

Pipeline order:
1. load recent messages and memory snapshot
2. parse turn (`ParserService`)
3. run policy (`PolicyEngine`)
4. execute direct tool or map search
5. compose assistant response
6. persist structured payloads

### Parser Layer

- `AEGIS/server/services/agent/parser_service.py`
- `AEGIS/server/services/agent/parser_rules.py`

Parser is evidence-only and returns `TurnParseResult`.

### Policy Layer

- `AEGIS/server/services/agent/policy_engine.py`
- `AEGIS/server/services/agent/location_resolver.py`
- `AEGIS/server/services/agent/capability_retriever.py`
- `AEGIS/server/services/agent/candidate_ranker.py`

Policy emits `PolicyDecision` + strict `ExecutionPlan`.

### Execution Layer

Map execution:
- `AEGIS/server/services/search/request_builder.py`
- `AEGIS/server/services/search/orchestrator.py`
- `AEGIS/server/services/search/execution.py`

Direct tools:
- `AEGIS/server/services/agent/tool_registry.py`
- `AEGIS/server/services/agent/tool_handlers/*.py`

## 4. Runtime Registry

`RuntimeRegistry` evaluates runtime readiness from `runtime_profiles.json` and credentials.

Checks include:
- enabled by default
- credential presence
- support mode (`map`, `direct_text`)
- provider health status
- tool handler name mapping

No hardcoded provider-specific branches are used as routing authority.

## 5. Coverage and Catalog

Coverage evaluation:
- `AEGIS/server/services/geospatial/coverage.py`

Catalog output:
- `AEGIS/server/services/geospatial/catalog.py`

Catalog exposes normalized descriptors for basemaps, overlays, and tools with availability, support modes, coverage, and tags.

## 6. API Contracts

Chat:
- `POST /api/chat/turn`
- `POST /api/chat/stream`

Maps:
- `GET /api/maps/catalog`
- `POST /api/maps/search`

Request/response contracts are strict and versioned in backend and frontend domain types.

## 7. Frontend Integration

Primary page:
- `AEGIS/client/src/app/pages/geospatial-page.component.ts`

Map renderer:
- `AEGIS/client/src/app/components/map-preview.component.ts`

The frontend consumes explicit decision/tool/map payloads and explicit `basemap_id`/`overlay_ids` from backend responses.

## 8. Persistence

Structured chat turn payloads are stored in existing JSON persistence fields through `ChatHistoryRepository`.

Location slot memory is persisted and restored from the same structured payloads.

No database schema migration is required for this workflow.

## 9. Test Coverage Focus

Primary coverage targets:
- parser rules and parser service
- location memory and resolver
- policy engine and retrieval/reranking
- capability/runtime/coverage registry behavior
- request builder and vector manifest preparation
- frontend rendering for clarification/direct-tool/map-session states
- persisted state invalidation on schema version changes
