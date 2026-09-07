# Troubleshooting

Last updated: 2026-09-07

## Basics

- If the application asks you to resize the browser, use a desktop window at
  least `1024px` wide. AEGIS does not provide a mobile layout.
- No response or failed request: verify backend and frontend are running.
- Local model issues: confirm the Ollama URL and run connection check in Settings.
- Missing expected model: refresh the model list or pull the model in Ollama settings.
- Unexpected state after auth failures: the app clears persisted state on 401 or 403 for safety.
- Missing geospatial integration: add the required provider key or use an available open-data alternative.
- A cloud provider catalog error: check the provider-specific source status in
  Settings. DeepSeek, OpenCode Zen, and OpenCode Go catalogs are fetched on
  request and can be unavailable even when the saved key is present.
- A layer warning or unchanged map: the upstream provider may have timed out,
  rate-limited, or returned invalid data. The app preserves the last valid map
  state instead of displaying a failed request as a successful layer.

## Operational Notes

- External data sources affect response quality and availability.
- SQLite database locked: wait for another startup or write operation to finish;
  the application uses WAL and a five-second busy timeout. Do not delete the
  database to clear a lock.
- SQLite database corrupt or unversioned: stop the application, copy the file
  for safekeeping, and either restore a known-good backup or set `AEGIS_DATA_DIR`
  to a new directory. Startup will not stamp or replace an existing file.
- SQLite database unwritable: verify that `AEGIS_DATA_DIR` exists or that its
  parent is writable by the launcher account.
- State persistence is session-based and tab-aware.
- During an active run, additional messages are steering updates. Reconnects
  resume the realtime WebSocket from the persisted sequence and suppress
  duplicate event IDs. A browser must use the configured UI origin and
  `aegis.realtime.v1` subprotocol; a rejected origin or missing subprotocol is
  an intentional protocol failure.

## Known Limitations

These limitations are intentional and remain part of the current product
contract:

- Direct `POST /api/chat/turn` keeps its existing immediate response behavior;
  AEGIS does not provide a second headless render-ack transport for that path.
- Antimeridian handling is provider-dependent. Providers may accept, reject, or
  interpret a bounding box crossing the antimeridian differently.
- Weather products that provide only point or metadata sampling cannot claim an
  area overlay.
- Flood comparisons require verified comparable measures, units, and time
  windows. When those semantics are not established, AEGIS asks for the layers
  separately or a clearly comparable data contract.
- FIRMS and other provider credential failures remain structured limitations;
  AEGIS does not silently replace the provider or invent a successful result.
- A valid empty result is distinct from an unavailable provider and is shown as
  an explicit no-results state in the assistant response, map panel, and layer
  controls.
- Browser acknowledgment is client-reported rendering evidence. Backend
  semantic validation remains authoritative for completion and committed map
  state.
