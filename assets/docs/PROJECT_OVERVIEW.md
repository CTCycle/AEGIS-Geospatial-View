# Project Overview

Last updated: 2026-05-24

## FILES INDEX

- AGENTIC_SEARCH.md  
  Action-aware chat orchestration architecture, provider-native tool calling, overlay tools, and internal agent responsibilities.

- API_ACCESS_AND_ACCOUNT_SETUP.md  
  Account setup, credential configuration, API key handling, quotas, restrictions, and official links for all external geospatial data providers.

- ARCHITECTURE.md  
  End-to-end technical architecture for frontend and backend, including module responsibilities, API surfaces, data persistence, and execution model.

- BACKGROUND_JOBS.md  
  In-process background job lifecycle, API contract, cancellation model, and operational constraints.

- CAPABILITY_MANIFESTS.md  
  Manifest schema and runtime-profile rules for basemaps, overlays, and tools under `app/resources/manifests`.

- GEOSPATIAL_SOURCE_CATALOG.md
  Source catalog for geographic intelligence providers, capability kinds, access modes, rendering modes, provider contract coverage, and integration status.

- GEOSPATIAL_INGESTION.md
  Manifest contract and planning flow for downloaded or preprocessed geospatial datasets.

- GEOSPATIAL_VALIDATION.md
  Static audit, provider contract, API, client, CI, and browser-smoke validation workflow for geospatial capabilities.

- WEBCAM_CAPABILITY.md
  Camera-network policy and implementation notes for Windy Webcams and future public camera providers.

- CODING_RULES.md  
  Unified coding standards across Python and TypeScript, including typing, validation, async boundaries, testing, and tooling.

- PROJECT_OVERVIEW.md  
  Documentation governance index and workspace-level rules for contextual reading and Windows operating assumptions.

- RUNTIME_MODES.md  
  Supported execution modes (local web stack and desktop packaging), startup commands, configuration differences, and deployment notes.

- STATE_PRESERVATION.md  
  Frontend persisted-state model, TTL and tab-ownership rules, and reset semantics.

- UI_STANDARDS.md  
  Enforceable UI design system derived from current Angular implementation: tokens, layout, components, responsiveness, and accessibility.

- UI_UX_AUDIT_REPORT.md  
  Current UX audit findings, verification notes, and improvement priorities for the implemented interface.

- USER_MANUAL.md  
  End-user operation guide for workspace, settings, and core chat-driven geospatial workflows.

## CONTEXT RULES

- Read documentation files only when needed for the current task.
- Defer deep reads until a concrete implementation or validation step requires them.
- Keep affected docs synchronized with code changes; update docs in the same change set when behavior changes.
- Include a `Last updated: YYYY-MM-DD` line whenever a document is modified.
- Do not read all `SKILL.md` files by default.
- Pre-select relevant docs based on folder structure (`app/server`, `app/client`, `app/tests`, `release`) and explicit user request.

## ARCHITECTURE NOTE

- The chat interface delegates map-aware requests to a provider-native tool-calling agent loop.
- Structured parsing and native tool calling are separate LLM execution paths.
- Capability manifests remain the source of truth for geospatial overlays and catalog/describe/execute agent tools.
- Ollama models are capability-checked before agent assignment; unsupported models cannot be selected for the agent role.

## ENVIRONMENT RULES

- Treat Windows as the default execution environment for commands, scripts, and troubleshooting.
- Provide command examples for both PowerShell and CMD when documenting operational workflows.
- Prefer PowerShell for structured inspection and automation (`Get-ChildItem`, `Select-String`, object pipelines).
- Use CMD syntax for existing `.bat` entry points (`start_on_windows.bat`, `app\tests\run_tests.bat`, `release\tauri\build_with_tauri.bat`).
- Document environment-specific decisions when discovered (for example, portable runtimes under `runtimes/`, lockfile sync flow, port-kill behavior).
- Keep paths and quoting Windows-safe in documentation (`\` separators, quoted paths for spaces).
