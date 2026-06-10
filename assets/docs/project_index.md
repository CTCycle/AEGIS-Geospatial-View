# Project Overview

Last updated: 2026-06-02

## Purpose

This file is the root index for `assets/docs`. Read it first, then open the smallest leaf document that answers the current question.

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
  Launcher, manual startup, test, and packaging commands.
- `runtime/configuration.md`
  Environment variables, settings files, and profile differences.
- `runtime/deployment.md`
  Packaging outputs, interoperability, and runtime constraints.

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
  Model settings, access configuration, and user-facing controls.
- `user/troubleshooting.md`
  Troubleshooting basics and operational notes for end users.

### Operations

- `operations/background_jobs.md`
  In-process job lifecycle, cancellation model, and operational constraints.

## Documentation Rules

- Keep file and folder names lower-case.
- Prefer narrow topic files over large omnibus documents.
- Update affected docs in the same change set as behavior changes.
- Include `Last updated: YYYY-MM-DD` whenever a document changes.
- Remove obsolete docs and QA artifacts from `assets/docs`; keep validation artifacts under root-level `QA/` when they must be preserved.

## Environment Rules

- Windows is the default operating environment.
- Keep PowerShell and CMD examples aligned with actual repo entry points.
- Document environment-specific constraints when they affect runtime, validation, or packaging.
