# Settings And Access

Last updated: 2026-09-16

## Geospatial Access

The Geospatial Access tab at `/settings?tab=geospatial-access` is for optional
geospatial provider keys such as TomTom and OpenAQ. The default workflow
remains usable without them. Setup notes, official documentation links, and
the guided signup workflow remain manifest-driven; documentation-only
providers stay manual.

## Models Workflow

1. Open Settings and choose Models.
2. Choose Cloud or Local mode through provider selection.
3. Search or filter models.
4. Select one model card as the AEGIS agent model.
5. Ensure the selected model supports tool calling and structured output.
6. For local mode, manage Ollama URL, check connection, refresh models, or pull a model.
7. Save credentials or Ollama settings if needed, then return to chat.
8. When `DeepSeek`, `OpenCode Zen`, or `OpenCode Go` is selected in model filters or as the agent model, AEGIS loads the compatible models from the configured provider account.
9. OpenCode catalogs expose the live intersection of the published model table and the provider account. AEGIS supports OpenAI-compatible Chat Completions and Responses models; Anthropic Messages, provider-specific Gemini transports, and unknown protocols remain visible as disabled selections with an explanation.
10. If a dynamic cloud catalog cannot be loaded, Settings keeps its provider filter active and shows the provider-specific error instead of a generic empty-state message.
11. Use `Test selected model` in the selected-model panel to run the real
    native structured-response probe. A selected model remains selectable before it is
    probed and is labeled `Not verified`; failed, timed-out, or unsupported
    probes show `Needs attention`. Probe results expire after 15 minutes and
    never switch the selected model or provider automatically.

An unavailable dynamic catalog does not erase a previously configured model.
Re-enter a provider key only when Settings reports missing or undecryptable
credentials; a valid key is not proof that the upstream catalog or inference
endpoint is currently healthy.

OpenCode Go identifies DeepSeek V4.1 Flash with the canonical mapping
`DeepSeek V4.1 Flash` → `deepseek-v4.1-flash`. The ID is accepted only when
it is returned by the live OpenCode Go `/models` catalog; the registry supplies
its documented OpenAI-compatible Chat Completions transport metadata and does
not seed or force an application default. OpenCode requests identify AEGIS with a versioned `User-Agent` and carry a
stable `x-opencode-session` value for the conversation. The session is reused
for retries and later turns, while catalog discovery sends only the
`User-Agent`. AEGIS never silently substitutes a model or provider when a
saved selection is retired, absent from the live catalog, or uses an
unsupported transport; select a replacement deliberately.

Catalogue reachability and inference readiness are separate signals. A model
catalogue can be reachable while its native structured-response probe has not been run
or has failed. Settings reports the probe independently of catalogue loading
and credential presence.

## User-Facing Controls

### Chat Composer

- `Enter`: send message
- `Shift+Enter`: newline

### Toolbar And Layout

- collapse or expand the left panel
- resize the toolbar width with the vertical handle
- use map zoom controls or chat zoom commands

### Settings Controls

- Models tab: model search, provider filters, model cards, selected-agent
  summary, native structured probe, and Ollama model pull actions.
- Model Providers tab: inline masked credentials for OpenAI, Google, DeepSeek,
  OpenCode Zen, and OpenCode Go, each with explicit Save and Clear actions;
  Ollama URL, health, refresh, and save controls. The default local loopback
  URL is `http://127.0.0.1:11434`.
- Geospatial Access tab: manifest-driven provider setup notes, documentation
  links, guided setup, and explicit masked credential Save/Clear controls.
- Blank credential drafts do not change saved keys. Clearing a credential is
  an explicit action. Saved values are never returned to or repopulated in the
  browser.
