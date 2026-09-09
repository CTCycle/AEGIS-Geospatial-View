# AEGIS native-agent autonomy implementation report

Date: 2026-09-09
Baseline: `1a802a35`
Implementation increment: `731ff9bd` plus the pending native-first increment
Historical audit: `AGENTIC_PIPELINE_AUDIT.md` (unchanged)

## Outcome

The native geospatial execution slice is implemented on `develop`. Tool-capable
runs now route through a native decision loop when the configured adapter
supports native tools; deterministic execution remains an explicit mode for
adapters that report no native-tool support. The native surface is eight focused
primitives, and model-visible results are bounded evidence envelopes rather than
raw provider payloads.

## Architecture diagnosis and remediation

The pre-change audit identified deterministic-first ordering, premature textual
stops, fixed history truncation, character-prefix tool-result truncation, and no
durable evidence boundary as the main autonomy failures. The implementation now
separates interpretation/policy invariants, native decisions, and deterministic
validation/persistence. It adds conversation-scoped compressed evidence with
checksums, provenance and parent references; rebuilds working state and tool
schemas after every native observation; evaluates proposed textual stops against
completion requirements; and preserves map candidates until browser render
acknowledgement.

The old five-tool registration and
`render_geospatial_provider_layer` path were removed. The canonical native
tools are location resolution, capability discovery/description/execution,
provider-layer discovery, evidence inspection/transformation, and map
preparation.

## Context, timeout, and trace contracts

- Known models use the smaller of their declared input window and a 64K
  application working-set ceiling; unknown models use 32,768 tokens.
- Parser, native-loop, and synthesis requests use 24K, 64K, and 32K input
  ceilings respectively, with output/tool/schema/safety reservations.
- Evidence summaries receive the first 50% of remaining working capacity,
  recent conversation 35%, and structured history 15%, with unused capacity
  reassigned. Mandatory state is never silently dropped.
- Run profiles start at 90 seconds and promote once to 150 seconds (simple) or
  300 seconds (complex). Model, tool, map, synthesis, persistence, and render
  boundaries are centralized in typed `agent_execution` settings.
- Iteration traces contain sanitized tool exposure, result status, evidence
  references, pending requirements, retries, context usage, and stop evaluation.

## Validation evidence

| Gate | Result |
|---|---|
| Strict Pyright (`app/server/pyproject.toml`) | PASS — 0 errors |
| Ruff (`app/server`, `app/tests/unit`) | PASS |
| Backend unit suite | PASS — 919 passed, 2 warnings |
| Angular unit suite | PASS — 214 passed |
| Angular production build | PASS |
| OpenAPI regeneration | PASS; `app/shared/openapi.json` updated |
| Alembic heads | PASS — one head `202609090001` |
| Whitespace (`git diff --check`) | PASS |
| Live configured-provider matrix | NOT RUN — no provider/credential substitution permitted |
| Real-app browser MapLibre matrix | NOT RUN in this increment — requires the configured app services and browser session |

The controlled unit and contract gates prove routing, evidence ownership,
dynamic schemas, context allocation, stopping/recovery, render-timeout state,
and frontend contract behavior. They do not claim live-provider reliability or
real-browser rendering; those rows remain explicitly unavailable in the matrix.

## Remaining limitations

Live provider/model execution and the full real-app browser matrix still need to
be run with the configured runtime profile. No provider, model, credential,
network source, or fallback model was substituted to manufacture those results.
