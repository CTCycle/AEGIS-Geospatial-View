# AEGIS custom agent runtime v2

AEGIS keeps one orchestrating agent.  Planning, scheduling, validation, and
checkpointing are ordinary typed Python services; no LangGraph/LangChain agent
runtime is introduced.

```mermaid
flowchart TD
  U["User turn or steering update"] --> C["Resolve thread state and classify change"]
  C --> P["Structured parse and complexity gate"]
  P --> T["Create or revise typed task graph"]
  P --> D["Compile one deterministic task"]
  T --> S["Select runnable task"]
  D --> S
  S --> F["Deterministically filter capabilities"]
  F --> V["Validate arguments and policy"]
  V --> E["Execute with timeout and bounded retry"]
  E --> N["Normalize result and persist evidence"]
  N --> R["Reduce state and checkpoint"]
  R --> Q{"Completion valid?"}
  Q -->|Next task| S
  Q -->|Gap or invalidation| T
  Q -->|Clarification| H["Return unresolved question"]
  Q -->|Complete or partial| Y["Grounded synthesis and validated renderables"]
```

## State boundary

`server.domain.agent.runtime` owns the v2 contracts:

- `AgentThreadState` is durable conversation state (`schema_version=2`) and
  contains the goal, dependency-aware tasks, geospatial working state, evidence
  references, assumptions, unresolved questions, and active map session.
- `AgentRunState` is per-execution state: budgets, counters, canonical call
  fingerprints, plan revision, no-progress detection, and completion reason.
- `GeospatialWorkingState` keeps locations, scope/bounds/radius/CRS, exclusions,
  candidates, selected places, data sources, layers, features, temporal limits,
  and renderable references first-class.

The persisted conversation task snapshot is now v2 only.  There is no reader or
fallback for the former turn-ledger snapshot; local development data should be
recreated when the schema changes.

## Scheduling and safety

Task graphs are validated for unique IDs, missing dependencies, and cycles.
Dependent tasks run only after every required predecessor is `completed`; a
failed predecessor blocks dependents.  Tool calls are fingerprinted from a
canonical JSON representation, so a successful or non-retryable failed call is
not repeated.  Transient retries are bounded and delayed by 250 ms.

The native loop applies simple-run and complex-run budgets, a wall-clock budget,
and a two-step no-progress stop.  Tool argument/domain validation remains in
application code and occurs before a handler is called.

## Context and evidence

The model receives the current request, active directives, compact v2 task state,
relevant geospatial evidence, unresolved failures, and a bounded recent-message
window.  Raw payloads remain addressable through evidence references and are not
re-injected on every iteration.

## Observability

`RunEventType.TRACE` and `RunEventType.CHECKPOINT` are internal durable events.
They record the objective, checkpoint state hash, task snapshot, completion
reason, model/tool counts, and operational decisions.  They never contain hidden
chain-of-thought or credentials and are not fanned out to the user stream.

## Provider contract

The OpenAI Responses adapter uses Responses-native top-level function tools and
`function_call` / `function_call_output` input items.  Responses output items
are retained for the next iteration, while Chat Completions-shaped adapters
remain isolated to their own providers.

## Research basis

The design combines observation-driven ReAct execution with selective
Plan-and-Solve decomposition.  It follows the current official guidance on
structured function calling, context engineering, task-specific evaluation,
and trace separation.  Frameworks such as LangGraph were used only as
architectural references for thread/run/checkpoint separation.
