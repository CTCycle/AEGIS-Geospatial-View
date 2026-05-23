# Long-Run Validation Report

Last updated: 2026-05-16

## Scope

End-to-end UI validation was run against the local web stack on May 16, 2026, using the visible application plus browser-driven interaction and rendered screenshots. The pass covered model selection, key handling, normal chat, geospatial search, map overlays, multilingual/noisy input, and resilience to missing credentials or imperfect requests.

## Environment

- Frontend: `http://127.0.0.1:4512`
- Backend: `http://127.0.0.1:7059`
- Local model used for broad validation: `qwen2.5:7b`
- Additional local smoke model: `smollm2:135m`
- Cloud model requested: `gpt-4.1-mini`
- Cloud-key state: only a dummy OpenAI key was available, so full cloud chat/search validation was stopped after confirming graceful invalid-key handling.

## Executive Summary

The application is broadly usable with local Ollama models and open-data basemaps, but the validation exposed several high-value issues:

1. API-key saves were blocked by unrelated stale Ollama assignments.
2. Installed Ollama models were hidden in Settings because the UI rendered only catalog models, not installed tagged variants.
3. Invalid cloud credentials were reported as a generic “parser unavailable” error instead of an authentication problem.
4. Satellite-imagery sessions rendered as visually blank maps in live UI screenshots even when the assistant reported success.
5. Some requests received low-quality or overconfident geospatial decisions, including irrelevant default overlays and ambiguous place resolution without clarification.
6. Non-search conversational context is shallow; a follow-up question did not preserve the prior turn naturally.

The first three issues were fixed during the pass and retested through the UI.

## Validation Results

| Case | Prompt / Action | Model | Expected | Actual | Evidence | Severity | Retest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Model selection: local | Open Settings, select installed local model | `smollm2:135m` | Installed local model visible and assignable | Initially hidden; fixed so installed models now render under **OLLAMA · INSTALLED** | `validation-ollama-installed.png` | High | Passed after fix |
| Model selection: cloud | Select `gpt-4.1-mini` | `gpt-4.1-mini` | Cloud model selectable | Selectable, but full run blocked by invalid dummy key | `validation-settings.png` | Environment-blocked | Stopped per plan |
| Dummy API key insertion | Enter/save dummy OpenAI key | n/a | Input accepted, persisted, invalid key handled gracefully | Initially blocked by stale unavailable local model; fixed. Persistence then worked and key remained configured after refresh | `validation-api-key-modal.png` | High | Passed after fix |
| Normal chat | “What can you do?” | `smollm2:135m`, later `qwen2.5:7b` | Clear answer without map/search | Passed | `validation-local-chat.png` | None | n/a |
| Multi-turn normal chat | “What can you do?” → “Can you answer normal questions too?” → “What did I just ask you?” | `qwen2.5:7b` | Maintain basic conversational context | Third answer repeated a generic capability response rather than answering the previous-turn question | `validation-chat-sequence.png` | Medium | Not fixed |
| Invalid cloud key | Ask a simple prompt with dummy OpenAI key | `gpt-4.1-mini` | Explain invalid key clearly | Initially showed misleading “parser unavailable”; fixed to explicit rejected-key message | `validation-invalid-openai-chat-fixed.png` | Medium | Passed after fix |
| City search | “Show me Rome, Italy on the map.” | `qwen2.5:7b` | Correct place and useful rendered map | Place resolved, but unrelated U.S./EU overlay bundle was selected | `validation-map-rome.png` | Medium | Not fixed |
| Address search | “Show me 1600 Pennsylvania Avenue NW, Washington, DC.” | `qwen2.5:7b` | Correct address and rendered map | Passed visually on OSM basemap | `validation-map-address.png` | None | n/a |
| Coordinate search | “Show me 41.9028, 12.4964 on the map.” | `qwen2.5:7b` | Correct point and rendered map | Coordinates resolved, but satellite basemap rendered visually blank | `validation-map-coords.png` | High | Not fixed |
| Weather + traffic typo/multilingual | “Mostrami Firenzze con meteo e traffico.” | `qwen2.5:7b` | Recover typo, render useful overlays, explain missing keys | Recovered to Firenze and explained missing TomTom key clearly | `validation-typo-multilingual.png` | None | n/a |
| Webcam overlay | “Show webcams around Reykjavik, Iceland.” | `qwen2.5:7b` | Use webcam capability or explain unavailable state | No overlays were added and no useful explanation was given | `validation-overlay-webcams.png` | Medium | Not fixed |
| Amenities overlay | “Show cafes and amenities near Shibuya, Tokyo.” | `qwen2.5:7b` | Useful POI overlays | Overlay names selected, but visible map value was limited because both were surfaced as metadata/setup-only | `validation-overlay-amenities.png` | Medium | Not fixed |
| Flood + demographics | “Show flood and demographic layers for Des Moines, Iowa.” | `qwen2.5:7b` | Relevant overlays and readable map | Mostly relevant; FEMA layer explained as incomplete provider metadata | `validation-overlay-flood-demo.png` | Low | n/a |
| Satellite + fires | “Show satellite imagery and active fires over Manaus, Brazil.” | `qwen2.5:7b` | Satellite map plus fire overlays | Fire overlays selected, but the satellite basemap screenshot was blank | `validation-overlay-satellite-fires.png` | High | Not fixed |
| Air quality + weather | “Show air quality and weather for Nairobi, Kenya.” | `qwen2.5:7b` | Relevant overlays, clear unsupported states | Relevant layers selected; unsupported NOAA radar explained | `validation-overlay-air-weather.png` | Low | n/a |
| Spanish input | “Muéstrame Madrid con lluvia actual.” | `qwen2.5:7b` | Handle Spanish and retrieve weather layers | Passed with sensible rain/weather overlays | `validation-resilience-spanish.png` | None | n/a |
| Ambiguous place | “show me paris” | `qwen2.5:7b` | Clarify only if needed | Chose Paris confidently; acceptable for common usage, but still overlaid irrelevant demographic defaults | `validation-resilience-ambiguous.png` | Low | n/a |
| Informal typo + ambiguous city | “can u show traficc near naples pls” | `qwen2.5:7b` | Recover typo and avoid wrong city when ambiguous | Chose Naples, Florida without asking whether the user meant Naples, Italy | `validation-resilience-informal-typo.png` | Medium | Not fixed |
| Mixed-language input | “Mostra Berlin weather bitte” | `qwen2.5:7b` | Handle mixed-language phrasing | Passed | `validation-resilience-mixed-language.png` | None | n/a |
| Malformed coordinates | “show 41,9028; 12,4964 on map” | `qwen2.5:7b` | Recover decimal separators if possible | Correctly normalized to `41.9028, 12.4964`; satellite rendering still blank | `validation-resilience-bad-coords.png` | Mixed | Partial |

## Bugs Found and Fixes Applied

### Fixed 1: API-key saves blocked by stale local assignments

- **Problem:** Saving an API key reused the full settings payload. If a previously assigned Ollama model was no longer installed, the backend rejected the entire update even though the user was only editing credentials.
- **Impact:** Users could not repair or replace credentials until they first fixed an unrelated local-model assignment.
- **Fix:** The backend now blocks only newly introduced unavailable local assignments, not unchanged pre-existing ones.
- **Files changed:** `app/server/api/chat.py`
- **Retest:** Dummy OpenAI key could be saved and persisted after refresh.

### Fixed 2: Installed Ollama models hidden in Settings

- **Problem:** The Settings page rendered only catalog models and matched “installed” state by exact IDs. Installed tagged models such as `qwen2.5:7b` were present in the API response but invisible in the UI.
- **Impact:** Users could not reliably choose already-installed local models and were steered toward unnecessary pulls.
- **Fix:** The UI now merges installed local models with the public catalog and displays them under **OLLAMA · INSTALLED**.
- **Files changed:** `app/client/src/app/pages/settings-page.component.ts`
- **Retest:** Installed models rendered and were assignable from the UI.

### Fixed 3: Invalid cloud keys reported as generic parser outages

- **Problem:** A rejected OpenAI key produced the same user-facing message as an unavailable parser model.
- **Impact:** Users were told to refresh/pull Ollama when the real issue was an invalid cloud credential.
- **Fix:** Parser-authentication failures are now classified separately and surfaced with a specific rejected-key message.
- **Files changed:** `app/server/services/agent/parser_service.py`, `app/server/services/agent/orchestrator.py`
- **Retest:** Invalid dummy OpenAI key now produces a direct “saved API key was rejected” explanation.

## Open Issues Requiring Follow-up

### High priority

1. **Satellite imagery visually blank in live UI**
   - Reproduced with coordinate and Manaus prompts.
   - Assistant reports a successful map, but the visible canvas remains empty/dark.
   - Needs renderer/provider investigation with tile/network diagnostics.

2. **Default overlay selection is often irrelevant**
   - Rome, Paris, address, and coordinate prompts frequently added U.S.-centric or metadata-only overlays without user asking for them.
   - This degrades usefulness and creates clutter.
   - Likely needs stronger policy defaults around “basemap only unless the request asks for thematic layers.”

### Medium priority

3. **Ambiguous location handling is too confident**
   - “Naples” resolved to Naples, Florida without clarification.
   - This is exactly the kind of noisy-input case where a short clarification would improve trust.

4. **Webcam requests fail silently**
   - “Show webcams around Reykjavik” returned no overlays and no useful explanation.
   - The assistant should either select the webcam capability or explain missing credential/runtime support.

5. **Normal-chat context is shallow**
   - “What did I just ask you?” did not answer from recent context.
   - Current general-question shortcut appears to bypass conversational continuity.

## Screenshot Inventory

- `assets/docs/validation/long-run-2026-05-16/validation-initial.png`
- `assets/docs/validation/long-run-2026-05-16/validation-settings.png`
- `assets/docs/validation/long-run-2026-05-16/validation-api-key-modal.png`
- `assets/docs/validation/long-run-2026-05-16/validation-ollama-modal.png`
- `assets/docs/validation/long-run-2026-05-16/validation-ollama-installed.png`
- `assets/docs/validation/long-run-2026-05-16/validation-local-chat.png`
- `assets/docs/validation/long-run-2026-05-16/validation-invalid-openai-chat.png`
- `assets/docs/validation/long-run-2026-05-16/validation-invalid-openai-chat-fixed.png`
- `assets/docs/validation/long-run-2026-05-16/validation-map-rome.png`
- `assets/docs/validation/long-run-2026-05-16/validation-map-address.png`
- `assets/docs/validation/long-run-2026-05-16/validation-map-coords.png`
- `assets/docs/validation/long-run-2026-05-16/validation-typo-multilingual.png`
- `assets/docs/validation/long-run-2026-05-16/validation-overlay-webcams.png`
- `assets/docs/validation/long-run-2026-05-16/validation-overlay-amenities.png`
- `assets/docs/validation/long-run-2026-05-16/validation-overlay-flood-demo.png`
- `assets/docs/validation/long-run-2026-05-16/validation-overlay-satellite-fires.png`
- `assets/docs/validation/long-run-2026-05-16/validation-overlay-air-weather.png`
- `assets/docs/validation/long-run-2026-05-16/validation-resilience-spanish.png`
- `assets/docs/validation/long-run-2026-05-16/validation-resilience-ambiguous.png`
- `assets/docs/validation/long-run-2026-05-16/validation-resilience-informal-typo.png`
- `assets/docs/validation/long-run-2026-05-16/validation-resilience-mixed-language.png`
- `assets/docs/validation/long-run-2026-05-16/validation-resilience-bad-coords.png`
- `assets/docs/validation/long-run-2026-05-16/validation-chat-sequence.png`

## Recommendation

The next best iteration is not broader scenario coverage; it is a focused remediation pass on the remaining user-visible defects:

1. diagnose and fix blank satellite rendering,
2. tighten overlay-selection policy defaults,
3. add clarification behavior for genuinely ambiguous locations,
4. improve “no webcam available” messaging,
5. restore context-aware behavior for simple non-map follow-ups.
