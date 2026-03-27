# AEGIS Documentation General Rules

This file defines mandatory rules for documentation and engineering work in this repository.

## 1. Required Review Order

Before any task:
1. Read `assets/docs/GENERAL_RULES.md`.
2. Read only the additional docs required by the task scope.

Use this map:
- `ARCHITECTURE.md`: system layout, APIs, data flow, persistence.
- `BACKGROUND_JOBS.md`: async/background search job lifecycle.
- `GUIDELINES_PYTHON.md`: backend/service Python rules.
- `GUIDELINES_TYPESCRIPT.md`: frontend/service TypeScript rules.
- `GUIDELINES_TESTS.md`: test execution and test-writing conventions.
- `PACKAGING_AND_RUNTIME_MODES.md`: launcher, Docker, and env profiles.
- `UI_STANDARDS.md`: frontend visual, layout, and accessibility standards.
- `README_WRITING.md`: README structure and quality requirements.
- `UI_UX_AUDIT_REPORT.md`: current UI/UX status snapshot and known issues.

## 2. Source of Truth and Consistency

- Keep `assets/docs` aligned with the actual code in `AEGIS/`, `tests/`, and runtime scripts.
- Prefer concrete references (real paths, routes, env keys, versions) over generic guidance.
- If two docs overlap, they must agree on terminology and behavior.
- Remove stale product names and outdated implementation details.

## 3. Documentation Update Triggers

Update relevant docs whenever changes affect:
- API routes, payloads, or error behavior.
- Runtime setup, ports, environment variables, or packaging workflow.
- UI structure, navigation model, or design tokens.
- Test flow, tooling, or required prerequisites.
- Architecture boundaries, service ownership, or persistence model.

## 4. Engineering Baselines

- Use PowerShell for commands unless `.bat`/CMD syntax is required.
- Keep changes small and scoped to the task.
- Prefer reproducible commands and verifiable outcomes.
- Follow secure defaults: validate inputs, do not hardcode secrets, minimize exposed surfaces.

## 5. Skills Usage

When a task maps to an available skill, use that skill guidance. Keep usage pragmatic and scoped.

## 6. Final Check Before Completion

Before finishing a docs task, ensure:
- Terminology is consistent across files (project name, module names, runtime versions).
- Route and path references match existing code.
- Dates and scope labels reflect current intent (do not leave obsolete "pre-implementation" text when no longer true).
