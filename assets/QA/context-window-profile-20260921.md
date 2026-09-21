# Context-window profile validation

Date: 2026-09-21
Branch: `loop-dev`
Environment: local application launched through the existing Windows launch path; Codex in-app Browser at `http://127.0.0.1:4512`

## Browser-visible evidence

| Scenario | Result | Evidence |
| --- | --- | --- |
| Exact configured OpenAI catalog entry | PASS | Selecting `openai / gpt-4.1` showed `Context 1.05M tokens`; the detail text showed the exact `1,047,576` token limit and source `openai_model_catalog`. |
| Known profile before a request | PASS | The profile was visible immediately after model selection; no request was required. |
| Start a new chat | PASS | The `1.05M tokens` indicator remained visible after starting a new chat. |
| Restore the original OpenCode selection | PASS | Restoring `opencode-go / deepseek-v4.1-flash` returned `Context Unavailable`, with the selected provider/model shown in the detail text. This is expected because the live descriptor did not provide an authoritative limit. |
| Model card formatter | PASS | The Settings card displayed `Max context: 1.05M tokens` for `gpt-4.1`; unknown OpenCode cards displayed `Context: provider limit not reported`. |

The two states above were captured as browser-visible screenshots in the Codex in-app Browser. The Browser tool exposes those captures inline but does not provide a local image export API, so no binary screenshot is claimed here. The API snapshots and the visible-state observations are preserved below.

## API evidence

Redacted settings captures are in [context-window-profile-20260921-settings.json](./context-window-profile-20260921-settings.json). No credentials or provider secrets were recorded.

## Validation status

- PASS: focused backend context-budget, resolver, model-library, provider, settings, agent-loop, API-contract, and terminal-response coverage.
- PASS: frontend focused tests: 70 successful tests.
- PASS: frontend production build.
- PASS: Ruff on the changed backend/test paths.
- PASS: OpenAPI regeneration; the diff contains only the new optional authority fields.
- PASS: live local browser selection, formatter, model identity, and new-chat retention checks.
- UNRUN: live Ollama `/api/show` scenarios; no Ollama model/server was available in this environment.
- UNRUN: live provider inference request; the browser checks intentionally used settings/model selection only.
- PARTIAL: the full backend unit suite reached 890 passed and one failure in the repository hygiene test because pre-existing ACL-protected generated files remain under `app/tests/cache`. No implementation test failed.
- PARTIAL: whole-project Pyright retains one unrelated pre-existing error in `app/server/services/agent/tool_handlers/location.py:118`.
