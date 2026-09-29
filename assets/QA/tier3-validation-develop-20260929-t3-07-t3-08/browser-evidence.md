# Browser evidence boundary

The existing Windows test infrastructure started an isolated backend and frontend on `127.0.0.1:7059` and `127.0.0.1:4512`. The browser tests verified the configured lane through `/api/chat/models/structured-probe` before sending map prompts.

Observed probe:

```json
{"http_status":200,"provider":"","model":"","protocol":"unknown","status":"failed","parse_status":"failed","duration_ms":0}
```

The required `opencode-go / deepseek-v4.1-flash` lane was not available. The FEMA/ESA diagnostic recorded one skipped test and the 12-layer NASA GIBS matrix recorded 12 skipped tests. No prompt reached the renderer acceptance phase.

Consequently, the following are intentionally `unobserved`, not inferred:

| Evidence item | Result |
| --- | --- |
| AEGIS proxy request | Unobserved; zero live proxy requests |
| HTTP response/status/content type | Unobserved |
| MapLibre source state | Unobserved |
| MapLibre layer state | Unobserved |
| Visible raster pixels | Unobserved |
| Attribution in rendered map | Unobserved |
| `map.render_ack` | Unobserved |
| Screenshot | None produced |

This package therefore does not promote either live gate. The local frontend regression and backend proxy tests prove generic contracts only; they are not browser raster-render evidence.
