# Native AEGIS harness implementation bootstrap

Last updated: 2026-09-14

## Purpose

This is the resume point for the native-agent consolidation work in
`CTCycle/AEGIS-Geospatial-View`. Continue from the commits below; do not
rebuild completed slices or introduce another compatibility architecture.

The target is one native harness, one canonical run state, one tool registry,
one context manager, one observation contract, one timeout/budget policy, and
one public response contract. Do not introduce LangGraph, the OpenAI Agents
SDK, or another external agent runtime.

## Starting point

- Branch: `develop`
- Resume commit: `84b6da26` (`chore(agent): remove native shadow preview path`)
- Audit baseline: `c6809755e1ea2dafdc09e45f0f4c574d5327f04f`
- No push, PR, merge, or release was performed.
- The only known pre-existing untracked worktree content is `app/assets/`.
  Do not stage, delete, or reset it while resuming this work.

Production settings now default to `native_v2`. The shadow-preview
implementation was deleted from the orchestrator, loop, and dedicated test.
The `agent_loop_mode` setting and native/legacy switch still exist, so
`shadow` is a stale configuration value and must not be selected.

## Completed slices

- Native model-facing observations preserve bounded discovery, evidence,
  provider metadata, warnings, pagination, errors, recovery, and valid-empty
  semantics. Structured fields are bounded before serialization.
- Native recovery distinguishes correction, alternate-tool selection,
  replanning, clarification, and terminal failures.
- Empty deterministic capability shortlists can enter bounded discovery.
- Native state is hydrated from assembled conversation context, including
  directives, task state, map memory, summaries, messages, evidence outcomes,
  and context allocation telemetry.
- Model, tool, transition, and run-deadline budgets are enforced; history
  selection continues past oversized items; Responses continuation items are
  retained; matching in-flight runs can be cancelled.
- Provider timeout policy is injected from agent execution settings.
- Manifest routing domains are explicit and authoritative; legacy domain
  inference was removed and relevant manifests were updated.
- Provider-layer discovery and capability description were transferred to the
  native tool surface, with bounded pagination/evidence persistence and typed
  argument/execution contracts.
- Native map tools are gated by route presentation requirements, and native
  context allocations identify their execution phase.
- Native execution is the configured default; the shadow-preview path was
  removed in `84b6da26`.

Useful commits, newest first:

```text
84b6da26 chore(agent): remove native shadow preview path
b074be4d fix(agent): gate map tools by presentation route
b30e0cb4 refactor(agent): label context allocations by execution phase
33b21939 chore(agent): make native execution the default
bdc4f672 feat(agent): transfer capability descriptions to native tools
268e16ae feat(agent): transfer provider layer discovery to native tools
e3173c17 fix(agent): promote native run budgets after routing
aef9f3aa fix(agent): hydrate complete native context state
2b0d4125 fix(agent): rebuild hydrated context per model step
1bba0ec6 fix(agent): preserve provider continuation items
4a09207e fix(geospatial): unify provider timeout policy
61cbe094 fix(agent): keep fitting context history items
d3541a19 fix(agent): enforce native execution budgets
3a2098f7 fix(agent): preserve native observations and recovery paths
```

Earlier commits in the same sequence cover exact location-reference
validation, strict catalog metadata, native context telemetry, cancellation,
and the initial native context/goal contracts.

## Current architecture

The native core is `AgentLoop` plus typed contracts in `server.domain.agent`.
Its intended progressive tool surface is:

```text
route_request
resolve_location
discover_geospatial_capabilities
discover_geospatial_provider_layers
describe_geospatial_capability
execute_geospatial_capability
inspect_evidence
transform_evidence
apply_map_plan
```

The application is not yet single-source-of-truth. `AgentOrchestrator` still
contains `_run_native_v2_compat_turn` and the legacy path. Composition still
wires the older `NativeToolLoop` and `AgentToolCatalogService`, while
`ToolRegistry` still has the newer registered-tool collection and the older
`_native_tools` collection. Public response and task/state contracts still
contain migration-era projections.

Treat the remaining work as deletion-oriented consolidation, not as a reason
to add another execution mode.

## First resume task

Fix context hydration before deleting parser or task models:

1. In `app/server/services/agent/context_assembler.py`, include the calculated
   `constraints` as `policy_constraints=constraints` in the returned
   `AgentContextPackage`.
2. Add a focused assertion that `AgentStateFactory.create_from_context(...)`
   receives those constraints.
3. Run the context/state and native-loop tests, then commit this slice.

The assembler currently uses policy constraints in the mandatory context
budget, but the returned package omits them, so the native state factory cannot
hydrate them.

## Remaining implementation order

### P0: complete native semantics

1. Replace the compatibility route input with one native `AgentGoal` and a
   deterministic `CompletionContract`. Required obligations such as resolved
   location, temporal scope, operation, evidence retrieval, and map preparation
   must be compiled into state rather than inferred by the model.
2. Keep recovery observations in the loop long enough for correction,
   alternate-source selection, or replanning.
3. Bind exact location references, geographic scope, temporal boundaries,
   provider arguments, and task-owned filters server-side.
4. Add trajectory tests for discovery, timeout-to-alternate-source,
   valid-empty recovery, malformed-call correction, ambiguity clarification,
   render acknowledgement, and checkpoint/resume.

### P1: consolidate state and reliability

1. Collapse `AgentState`, runtime `AgentRunState`, task snapshots, and
   migration projections into one checkpointable run state plus one durable
   conversation state. Keep the model context ephemeral and derived per step.
2. Make one context manager own semantic compaction and evidence relevance;
   provider adapters should only enforce protocol limits.
3. Keep structured per-field bounds and distinct terminal budget reasons.
4. Add run-version checks at every external-action and state-commit boundary so
   cancellation and steering stop in-flight work promptly.

### P2: consolidate tools and manifests

1. Move any still-required live provider discovery behind the native discovery
   and description tools.
2. Reduce `ToolRegistry` to one registration/exposure/execution boundary;
   delete `_native_tools` and `register_native_tool`.
3. Delete `AgentToolCatalogService` after its required behavior and tests move
   to canonical handlers.
4. Keep schema-v2 `agenticUse.domains` strict; never restore `_legacy_domains()`.

### P3: delete migration code

Only after the native trajectory suite passes:

1. Make the native runner unconditional and remove `agent_loop_mode` and
   `_agent_loop_mode()`.
2. Delete the legacy parser/planner/executor chain and migration-only response
   projections once native goal/completion state covers their semantics.
3. Delete `NativeToolLoop` after transferring useful continuation, telemetry,
   no-progress, and dynamic-exposure behavior.
4. Remove dead tests, settings, comments, and docs describing legacy/shadow as
   supported modes.

## Validation

Use the existing `app/server/.venv` and a writable repository-local basetemp;
the managed Windows environment has recurring ACL failures in protected pytest
cache directories.

```powershell
git status --short
git log -8 --oneline
app\server\.venv\Scripts\python.exe -m ruff check --no-cache <changed-files>
app\server\.venv\Scripts\python.exe -m pytest -q --basetemp=assets/QA/pytest-native-bootstrap <focused-test-files>
git diff --check
git add -- <explicit-files>
git diff --cached --check
git commit -m "<scoped message>"
```

The last cleanup passed Ruff and `test_agent_loop_v2.py` (`16 passed`). A
broad `test_orchestrator_native_loop.py` run was not a clean product gate:
test settings without `agent_loop_mode` entered the legacy path, and the
managed environment raised `PermissionError` loading
`app/server/.venv/Lib/site-packages/tzdata/zoneinfo/UTC`. Re-run that suite
after the native path is unconditional and the environment ACL issue is
isolated.

Never stage `app/assets/` unless the user explicitly scopes that existing
untracked content into the task.

## Completion gate

Finish only when no runtime configuration or import path can select legacy or
shadow, and the application has one native loop, canonical state model,
registry, context/observation policy, budget/timeout policy, and public
response contract. The trajectory suite must cover recovery, context,
cancellation, map acknowledgement, provider continuation, and independent
budget limits.
