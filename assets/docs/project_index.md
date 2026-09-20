# Project Overview

Last updated: 2026-09-20

## Purpose

This file is the root index for `assets/docs`. Read it first, then open the smallest leaf document that answers the current question. For the current operational project state, read [`project_status_ledger.md`](project_status_ledger.md); detailed reports explain how each status was established.

## Current Implementation Snapshot

The runtime catalog currently contains 92 JSON documents: 6 basemaps, 48
overlays, 18 provider descriptors, 4 direct tools, 7 camera networks, 3
transit capabilities, and 4 reference catalogs. `runtime_profiles.json` adds
environment and credential availability on top of those manifests.

The implemented chat model surface includes static cloud catalog entries,
Ollama local models, and on-demand catalogs for DeepSeek, OpenCode Zen, and
OpenCode Go. Agent execution uses one native harness: a model-owned route,
progressively constrained typed tools, one normalized execution boundary, and
bounded evidence/result contracts. Legacy and shadow execution paths have
been removed. Normalized provider results and derived datasets live in the
conversation-scoped `agent_evidence` store rather than model messages.

## Navigation Rules

1. Start with this file only.
2. Choose one topic branch.
3. Open the narrowest leaf file under that branch.
4. Open sibling files only when the task clearly crosses boundaries.
5. Treat `app/resources/catalog` as the runtime source of truth for geospatial capabilities.

## Ontology

### Root

- `project_index.md`
  Root index, reading rules, and documentation governance.

### Operational Status

- [`project_status_ledger.md`](project_status_ledger.md)
  Canonical current operational status catalog for project components, active
  issues, resolved findings, and validation debt. Update it when implementation
  status, evidence, blockers, or remediation state changes.

### Architecture

- `architecture/system_overview.md`
  High-level system shape, tiers, entry points, and external integrations.
- `architecture/repository_structure.md`
  Repository layout and source-area inventory.
- `architecture/backend_api.md`
  HTTP endpoints, route contracts, and mounted API surfaces.
- `architecture/execution_and_data_flow.md`
  Layering rules, request flow, agent pipeline, geospatial pipeline, and async boundaries.
- `architecture/persistence.md`
  Relational, vector, model-capability, and frontend persistence details.
- `architecture/frontend_architecture.md`
  Route-level frontend structure, core modules, and state boundaries.

### Coding

- `coding/python.md`
  Python runtime, typing, validation, async, and structure rules.
- `coding/typescript.md`
  Angular and TypeScript architectural rules for frontend code.
- `coding/testing_and_quality.md`
  Linting, type-checking, build, and test expectations.
- `coding/cross_language.md`
  Shared backend/frontend contract and repository hygiene rules.

### Runtime

- `runtime/modes.md`
  Supported runtime modes and their operational differences.
- `runtime/startup.md`
  Launcher, manual startup, and test commands.
- `runtime/configuration.md`
  Environment variables, settings files, and profile differences.
- `runtime/deployment.md`
  Local distribution, interoperability, and runtime constraints.

### Geospatial

- `geospatial/agentic_search.md`
  Chat-to-tool orchestration model for geospatial requests.

#### Manifests

- `geospatial/manifests/capability_catalog.md`
  Reviewable inventory of providers, basemaps, layers, and direct tools.
- `geospatial/manifests/manifest_contract.md`
  Loader contract, maintenance rules, and capability metadata expectations.
- `geospatial/manifests/schema_v2.md`
  Required schema-v2 fields and strict manifest rules.
- `geospatial/manifests/reference_catalog.md`
  Seedable static catalog/reference data and startup seeding behavior.
- `geospatial/manifests/agent_catalog_contract.md`
  Stable native tools used to expose manifests to the agent.

- `geospatial/native_harness_bootstrap.md`
  Resume point, completed implementation slices, deletion order, and
  validation gates for the native-agent consolidation.

#### Providers

- `geospatial/providers/access_overview.md`
  Credential handling, access rules, setup automation boundaries, and exclusions.
- `geospatial/providers/public_and_optional_sources.md`
  Public and optional-provider setup guidance for live layers and tools.
- `geospatial/providers/statistical_and_ingestion_sources.md`
  Statistical, downloadable, and ingestion-oriented source setup guidance.
- `geospatial/providers/provider_framework.md`
  Provider adapter inventory and normalized response expectations.
- `geospatial/providers/webcams.md`
  Camera-network capability rules, API contracts, and rendering behavior.

#### Ingestion And Validation

- `geospatial/ingestion/dataset_ingestion.md`
  Dataset-ingestion manifest contract and execution pipeline.
- `geospatial/ingestion/validation.md`
  Manifest audit, backend, frontend, browser, CI, and live-provider validation workflow.

#### Validation Ledger

- [validation/gate_status.md](validation/gate_status.md)
  Canonical PASS/PARTIAL/FAIL/BLOCKED/UNRUN ledger for native-loop,
  presentation, browser-fault, provider, and hosted-CI gates. It is the
  detailed evidence ledger beneath the current component summary in
  `project_status_ledger.md`.

### UI

- `ui/design_tokens.md`
  Typography, spacing, color, and shared UI tokens.
- `ui/layout_and_navigation.md`
  Page layout, breakpoints, primary screens, and navigation hierarchy.
- `ui/components_and_patterns.md`
  Shared components, control states, and feedback patterns.
- `ui/experience_and_accessibility.md`
  UX rules, responsiveness, accessibility, and design principles.
- `ui/state_preservation.md`
  Session persistence, restore rules, tab isolation, and clear behavior.

### User

- `user/quick_start.md`
  Product purpose, primary screens, and fast onboarding path.
- `user/workflows.md`
  Core end-user journeys, chat patterns, and key features.
- `user/settings_and_access.md`
  Unified Models, Model Providers, and Geospatial Access settings controls.
- `user/troubleshooting.md`
  Troubleshooting basics and operational notes for end users.

### Operations

- `operations/background_jobs.md`
  In-process job lifecycle, cancellation model, and operational constraints.

## Documentation Rules

- Keep file and folder names lower-case.
- Prefer narrow topic files over large omnibus documents.
- Update affected docs in the same change set as behavior changes.
- Update `project_status_ledger.md` whenever a component status, active issue,
  blocker, validation result, or revalidation requirement changes. Keep detailed
  reports in `assets/QA/` and link them instead of duplicating their narratives.
- Include `Last updated: YYYY-MM-DD` whenever a document changes.
- Remove obsolete docs and QA artifacts from `assets/docs`; keep validation artifacts under root-level `assets/QA/` when they must be preserved.

## Environment Rules

- Windows is the default operating environment.
- Keep PowerShell and CMD examples aligned with actual repo entry points.
- Document environment-specific constraints when they affect runtime or validation.
