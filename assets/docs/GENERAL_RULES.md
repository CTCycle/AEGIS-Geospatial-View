# AEGIS Documentation General Rules

Last updated: 2026-04-08

This file defines mandatory documentation and engineering rules for this repository.

## 1. Complete Documentation Inventory

The `assets/docs` directory currently contains exactly these documentation files:

- `AGENTIC_SEARCH.md`
- `ARCHITECTURE.md`
- `BACKGROUND_JOBS.md`
- `GENERAL_RULES.md`
- `GUIDELINES_PYTHON.md`
- `GUIDELINES_TESTS.md`
- `GUIDELINES_TYPESCRIPT.md`
- `PACKAGING_AND_RUNTIME_MODES.md`
- `STATE_PRESERVATION.md`
- `UI_STANDARDS.md`
- `UI_UX_AUDIT_REPORT.md`
- `USER_MANUAL.md`

This list is exhaustive and must be updated whenever files are added, removed, or renamed in `assets/docs`.

## 2. Source of Truth and Consistency

- Keep `assets/docs` aligned with actual code in `AEGIS/`, `tests/`, and runtime scripts.
- Prefer concrete references (real paths, routes, env keys, versions).
- If two docs overlap, terminology and behavior must remain consistent.
- Remove stale or deprecated implementation guidance.

## 3. Documentation Update Triggers

Update affected docs when changes impact:
- API routes, payloads, or error behavior.
- Runtime setup, ports, environment variables, or packaging workflows.
- UI structure, navigation model, settings workflow, or UX behavior.
- Test tooling, runners, or prerequisites.
- Architecture boundaries, persistence model, or external integrations.

## 4. Engineering Baselines

- Keep changes scoped and verifiable.
- Use reproducible commands.
- Validate inputs and avoid hardcoded secrets.
- Preserve secure defaults and minimize accidental surface expansion.

## 5. Completion Checks

Before closing documentation work:
1. Verify doc references (paths/routes/commands) resolve to real code.
2. Ensure all docs include `Last updated`.
3. Ensure the inventory in this file is still complete and accurate.
4. Ensure root `README.md` stays user-oriented (setup + practical usage first).
