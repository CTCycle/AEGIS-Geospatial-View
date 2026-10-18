# Isolated settings and protected-state checks

## Runtime settings

| Checkpoint | `agent_execution.simple_max_model_calls` | Other runtime settings |
| --- | ---: | --- |
| Isolated copy before validation | 4 | Not changed |
| Temporary approved validation budget | 6 | Not changed |
| After restart with temporary budget | 6 | Not changed |
| Restored value before final restart | 4 | Not changed |
| After final restart and browser/API verification | 4 | Not changed |

The only persisted runtime field edited was
`agent_execution.simple_max_model_calls`. The final browser and local runtime
API both showed `4`; the exact provider/model selection remained
`opencode-go / deepseek-v4.1-flash`.

## Canonical repository state

- `settings/.env` SHA-256 before/after: `95D56835BADD0DD60AEDA6662D382BAFB0F76D3A75DA4D09B95F0165D98606FC`.
- Canonical `app/resources/runtime/database.db` remained 504,471,552 bytes with
  SHA-256 `68E4CB29E845F45247AA8AF98347FBFC929863BAC71048C8BB2959AF301DF32D`.
- The canonical runtime database was not used by the launcher or browser run;
  all mutable validation data lived under the isolated runtime directory.

No credentials or raw provider payloads were written to this evidence package.
