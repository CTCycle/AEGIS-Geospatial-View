# AEGIS native-agent autonomy baseline

Date: 2026-09-09
Commit: `1a802a35` (`develop`)
Historical audit: `AGENTIC_PIPELINE_AUDIT.md` (unchanged)

## Controlled baseline

The existing focused agent suite was run before implementation changes:

```text
64 passed, 1 warning in 4.84s
```

Command:

```text
app/server/.venv/Scripts/python.exe -m pytest -c app/server/pyproject.toml app/tests/unit/services/agent/test_context_assembler.py app/tests/unit/test_context_budget.py app/tests/unit/services/agent/test_native_tool_loop.py app/tests/unit/services/agent/test_agent_tool_catalog_service.py app/tests/unit/services/agent/test_orchestrator_native_loop.py -q
```

The test run used the repository-local writable pytest basetemp under
`assets/QA/pytest-agent-autonomy-baseline`.

## Pre-change behavior recorded from the current checkout

- Routing still selected deterministic `ToolPlanStep` execution before the
  native loop whenever a plan was available.
- The native loop accepted a no-tool model response as `stopped_reason=final`
  without evaluating pending task or presentation requirements.
- Native results were character-truncated before the next model request.
- The native catalog exposed five tools, including the legacy provider-layer
  render tool.
- Context assembly still contained the fixed 8,192-token history ceiling and
  the parser retained four recent messages at 640 characters each.
- Controlled render acknowledgement behavior was already covered by the
  existing MapLibre tests; live provider execution remains provider/configuration
  dependent and was not substituted for this baseline.

No provider, model, credential, network source, or historical audit file was
changed to produce this baseline.
