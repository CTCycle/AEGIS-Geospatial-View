# Persistence

Last updated: 2026-06-03

## Relational Storage

- Runtime selector: `app/server/repositories/database/backend.py`
- SQLite mode: `database.embedded_database: true`
- PostgreSQL mode: `database.embedded_database: false`
- SQLite implementation: `sqlite.py`
- PostgreSQL implementation: `postgres.py`

Database mode and connection settings come from `settings/configurations.json`. SQLite resolves through `server.common.constants.DATABASE_FILE_PATH`.

Schema initialization is handled by `app/server/repositories/database/initializer.py`.

## Core Stored Domains

Core relational storage covers:

- chat sessions and messages
- model provider settings
- encrypted model credentials
- manifest embedding records
- seeded geospatial reference data

## Reference Catalog Policy

- Static reference data belongs under `app/resources/catalog/reference`.
- Reference catalog loading, lookup, and startup seeding belong under `app/server/repositories/catalog/`.
- New catalog/reference constants should not be hardcoded in `app/server/common/constants.py`.
- Startup seeds empty reference tables from catalog files exactly once per table group.

## Vector Persistence

- Agent tool visibility does not depend on embeddings or vector ranking.

## Model Capability Persistence

- Cloud model capabilities are declared in `services/llm/cloud_catalog.py`.
- Ollama tool support is detected from provider capabilities or a cached probe.
- Agent assignment requires tool support.
- Parser assignment requires structured-output support.

## Frontend Persistence

- Storage key: `aegis:webapp-state:v3`
- Storage type: `sessionStorage`
- TTL: 6 hours
- Tab ownership guard: `localStorage` heartbeat keys
- Implementation: `app/client/src/app/core/app-state.ts`
