# Settings And Access

Last updated: 2026-10-21

## Geospatial Access

The Geospatial Access section at `/settings?tab=geospatial-access` is for optional
geospatial provider keys such as TomTom and OpenAQ. The default workflow
remains usable without them. Setup notes, official documentation links, and
the guided signup workflow remain manifest-driven; documentation-only
providers stay manual.

## Models Workflow

1. Open Settings and choose Models.
2. Choose Cloud or Local mode through provider selection.
3. Search or filter models.
4. Select one model card as the AEGIS agent model.
5. Review the selected-model summary for tool calling, structured output, vision,
   and the source of the tool-support metadata.
6. For local mode, manage Ollama URL, check connection, refresh models, or pull a model.
7. Provider credentials and the Ollama URL save automatically after a short pause; return to chat when ready.
8. When `DeepSeek`, `OpenCode Zen`, or `OpenCode Go` is selected in model filters or as the agent model, AEGIS loads the compatible models from the configured provider account.
9. OpenCode catalogs expose the live intersection of the published model table and the provider account. AEGIS supports OpenAI-compatible Chat Completions and Responses models; Anthropic Messages, provider-specific Gemini transports, and unknown protocols remain visible as disabled selections with an explanation.
10. If a dynamic cloud catalog cannot be loaded, Settings keeps its provider filter active and shows the provider-specific error instead of a generic empty-state message.

Tool support comes from the selected model's catalog or provider capability
metadata. Settings shows `detected`, `unavailable`, or `not verified` and names
the source in the selected-model summary. A model without a reported capability
remains selectable and `Not verified`; AEGIS does not send a test request to
resolve unknown metadata. Live behavior is learned during a normal workspace
request.

An unavailable dynamic catalog does not erase a previously configured model.
Re-enter a provider key only when Settings reports missing or undecryptable
credentials; a valid key is not proof that the upstream catalog or inference
endpoint is currently healthy.

OpenCode catalogs list every model returned by the live `/models` endpoint.
Each model's endpoint family (Chat Completions, Responses, or Anthropic
Messages) comes from the models.dev catalog that OpenCode itself publishes,
with the built-in table as the offline fallback; models neither source knows
use Chat Completions. Tool-calling readiness uses model capability metadata;
it does not send a test inference. Context limits
and image input also come from that catalog when `/models` omits them. Only
Google-protocol models stay disabled, with the reason shown on the card.
OpenCode requests identify AEGIS with a versioned `User-Agent` and carry a
stable `x-opencode-session` value for the conversation. The session is reused
for retries and later turns, while catalog discovery sends only the
`User-Agent`. When a model rejects the disabled-thinking control or a
non-default temperature, AEGIS records that from the provider's own response
and retries without it. AEGIS never silently substitutes a model or provider
when a saved selection is retired, absent from the live catalog, or uses an
unsupported transport; select a replacement deliberately.

Catalog reachability, reported tool support, and live inference are separate
signals. A reachable catalog can report tool support, report that it is
unavailable, or omit the capability. Omitted capability stays `Not verified`
until the catalog supplies metadata; workspace readiness does not run a probe
as a fallback.

## User-Facing Controls

### Runtime Settings

The eight Settings destinations are Models, Model Providers, Geospatial Access,
Application, Map & Search, Data Sources, Agent Runtime, and Database. Every
non-database setting saves automatically. Runtime controls save 400 ms after the
last edit and flush pending changes when leaving Settings. Provider credentials
and the Ollama URL use the same short debounce and also save when the field is
committed. Saving a provider key makes it available to new requests; provider
reachability is reported separately. Clearing a saved credential remains an
immediate, direct action because saved secret values are never returned to the
browser. Runtime settings are typed SQLite-backed blocks; each request sends
only changed fields and the server validates and commits the update atomically.

### Database

Database is the only settings category that requires explicit confirmation.
Edits stay in the form until `Apply and switch`; the server validates the
candidate file before activation and restores the previous configuration if
activation fails. The active connection settings live in
`database-settings.json` in the application data directory, independently of
the selected database. Database shows the active SQLite file, provides the
SQLite migration-lock timeout, and can test another file's access, integrity,
and schema before switching. Applying a switch initializes an empty database
at revision `202608200001`. Existing files must already use that revision;
other revisions are rejected and require an explicit rebuild or separately
reviewed migration. The app refuses to switch while API or WebSocket work or
active agent runs are present. Each file keeps its own settings and records;
switching never copies data. After activation the browser reloads so all
client-side settings come from the selected database.
SQLite is the only database backend currently implemented. Changing the
application data root or process-level service configuration still requires a
server restart.

Agent Runtime contains 31 controls covering execution budgets, failure
recovery, timeouts and retries, and advanced limits. Their defaults and the
complete field inventory are documented in
[`runtime/configuration.md`](../runtime/configuration.md). Agent-only changes
take effect for new runs without restarting AEGIS. A new run receives the
latest saved execution policy as an immutable snapshot; an active or
render-suspended run keeps the policy stored in its checkpoint. Execution
budgets and Failure recovery stay visible; Timeouts and retries, Advanced
limits, and Vision inspection start collapsed and open with the keyboard or
pointer.

Use `Restore agent defaults` to replace the Agent Runtime values with the
published defaults and save them immediately. Agent-only changes take effect
for new runs. Changes to Application, Map & Search, or Data Sources are saved
immediately and show a restart-required notice because those services are
composed at startup. The notice persists across page reloads and clears after
AEGIS restarts or the values return to the configuration loaded at startup.

### Chat Composer

- `Enter`: send message
- `Shift+Enter`: newline

### Toolbar And Layout

- collapse or expand the left panel
- resize the toolbar width with the vertical handle
- use map zoom controls or chat zoom commands

### Settings Controls

- Models section: model search, provider filters, model cards, selected-agent
  capability summary, and Ollama model pull actions.
- Model Providers section: inline masked credentials for OpenAI, Google, DeepSeek,
  OpenCode Zen, and OpenCode Go that autosave after a short pause, with a direct
  Clear saved key action; Ollama URL autosave, health, and model refresh
  controls. The default local loopback URL is `http://127.0.0.1:11434`.
- Geospatial Access section: manifest-driven provider setup notes, documentation
  links, guided setup, and masked credentials that autosave after a short pause,
  with a direct Clear saved key action.
- Blank credential drafts do not change saved keys. Clearing a credential acts
  immediately. Saved values are never returned to or repopulated in the browser.
