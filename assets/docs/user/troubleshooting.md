# Troubleshooting

Last updated: 2026-06-02

## Basics

- No response or failed request: verify backend and frontend are running.
- Local model issues: confirm the Ollama URL and run connection check in Settings.
- Missing expected model: refresh the model list or pull the model in Ollama settings.
- Unexpected state after auth failures: the app clears persisted state on 401 or 403 for safety.
- Missing geospatial integration: add the required provider key or use an available open-data alternative.

## Operational Notes

- External data sources affect response quality and availability.
- State persistence is session-based and tab-aware.
