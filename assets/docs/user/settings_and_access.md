# Settings And Access

Last updated: 2026-07-29

## Access Configuration

The Access page is for optional geospatial provider keys such as Geoapify and TomTom. The default workflow remains usable without them.

## Model Settings Workflow

1. Open Settings.
2. Choose Cloud or Local mode through provider selection.
3. Search or filter models.
4. Select one model card as the AEGIS agent model.
5. Ensure the selected model supports tool calling and structured output.
6. For local mode, manage Ollama URL, check connection, refresh models, or pull a model.
7. Save credentials or Ollama settings if needed, then return to chat.
8. When `DeepSeek`, `OpenCode Zen`, or `OpenCode Go` is selected in model filters or as the agent model, AEGIS loads the compatible models from the configured provider account.
9. OpenCode catalogs expose only models backed by the provider's OpenAI-compatible chat-completions endpoint, which is the protocol used for AEGIS tools, streaming, and structured output.
10. If a dynamic cloud catalog cannot be loaded, Settings keeps its provider filter active and shows the provider-specific error instead of a generic empty-state message.

## User-Facing Controls

### Chat Composer

- `Enter`: send message
- `Shift+Enter`: newline

### Toolbar And Layout

- collapse or expand the left panel
- resize the toolbar width with the vertical handle
- use map zoom controls or chat zoom commands

### Settings Controls

- provider mode toggle
- model search bar and provider filters
- API key modal for supported cloud providers, including dedicated DeepSeek, OpenCode Zen, and OpenCode Go key sections
- Ollama modal for URL, health, refresh, and model pull. The default local loopback URL is `http://127.0.0.1:11434`.
