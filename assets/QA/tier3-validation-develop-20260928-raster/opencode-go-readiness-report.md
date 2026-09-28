# Exact OpenCode Go readiness

Date: 2026-09-28
Branch: `develop`
Tested source: `develop@3de5619b`
Runtime data root: `app/resources`
Selected lane: `opencode-go / deepseek-v4.1-flash`

## Result

`PROVIDER-READY` is `PASS`. The earlier HTTP 401 was caused by stale local
credential state, not by the OpenCode Go endpoint or the AEGIS provider
adapter. The healthy canonical database contained an active OpenCode Go key
different from the supplied key. AEGIS reproduced the 401 when it decrypted
that stored value.

The supplied credential was saved through `PATCH /api/chat/settings`, using
the normal encrypted credential path. The response reported healthy
credential state without returning a secret. No provider or model fallback
was used.

## Evidence

- Relocated `app/resources/database.db` is 504,471,552 bytes, passes SQLite
  `integrity_check`, remains at Alembic revision `202609210001`, and retains
  the selected `opencode-go / deepseek-v4.1-flash` assignment.
- The final AEGIS catalog request returned `ok=true`, `reachable=true`, and
  30 provider models. `deepseek-v4.1-flash` was present with
  `openai-chat-completions`, tools support, and structured-output support.
- The final AEGIS native structured probe returned `status=passed`,
  `parse_status=complete`, and `message=Native tool probe passed.`
- The focused regression set passed **62/62** with one existing dependency
  deprecation warning.
- Ruff passed for the changed path-resolution and database-configuration
  files.

Machine-readable results are in [slice.json](opencode-go-readiness.json) and
[credential-path-check.json](credential-path-check.json). The earlier 401
result remains linked as historical diagnosis in [provider-probe.json](provider-probe.json);
it is not the final readiness status.

## Boundaries

This passes provider/catalog/native-probe readiness only. It does not claim a
fresh browser-authoritative FEMA/ESA MapLibre source/layer acknowledgement or
`map.render_ack`; those public-raster gates remain separate and incomplete.

The current checkout selects `app/resources` through `settings/.env`. Direct
relative `AEGIS_DATA_DIR` values now resolve from the repository root, matching
the Windows launcher. A process-level `AEGIS_DATA_DIR` override still takes
precedence and must point at a database containing the intended credential.
