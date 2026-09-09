# AEGIS native-agent autonomy implementation report

Date: 2026-09-09
Baseline: `f6448248`
Implementation increment: working tree E2E-enablement fix (uncommitted)
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
| Live geospatial provider matrix | EXECUTED — 30 checks: 11 passed, 5 failed, 14 skipped; strict exit reflects public-provider failures and unavailable configured sources; see `live-provider-matrix.json` |
| Configured-model live smoke | EXECUTED — HTTP 200 and persisted response in 37.1s using `opencode-go / deepseek-v4-flash`; structured extraction failed honestly with 0 tool/provider/map events; see `live-smoke-final/benchmark.json` |
| Real-app browser configured-model request | EXECUTED — Chrome visibly reached the configured app path; the model/tool path returned `Missing required argument 'target_id'`, with no map session; see `browser-live-20260909.md` |
| Controlled real-browser MapLibre render handshake | PASS — visible canvas, loaded USGS earthquake fixture, one rendered feature, valid viewport, `status=ready`, zero console errors; see `browser-maplibre-final/reports/controlled-map-completion.json` |

The controlled unit and contract gates prove routing, evidence ownership,
dynamic schemas, context allocation, stopping/recovery, render-timeout state,
and frontend contract behavior. The live rows now contain observed outcomes:
the configured provider/model was exercised without substitution, while the
controlled browser fixture separately proves the visible MapLibre render path.

## Remaining limitations

The configured live provider/model did not produce a successful map in this
increment: one smoke request stopped at structured response parsing, and the
real-browser request reached tool execution but failed on a missing `target_id`.
The geospatial provider matrix also contains five public-provider failures and
fourteen explicit configuration-dependent skips. These are recorded outcomes,
not substituted passes. No provider, model, credential, network source, or
fallback model was substituted to manufacture them.
