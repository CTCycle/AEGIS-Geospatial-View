# Browser evidence boundary

The isolated Windows test infrastructure ran the backend and frontend on
`127.0.0.1:7059` and `127.0.0.1:4512`. The browser tests verified the required
lane through `/api/chat/models/structured-probe` before sending map prompts.

Observed probe:

```json
{"http_status":200,"provider":"opencode-go","model":"deepseek-v4.1-flash","protocol":"openai-chat-completions","status":"passed","parse_status":"complete","duration_ms":3168}
```

## FEMA / ESA diagnostic

Both standalone prompts reached the AEGIS same-origin raster route. The
captured browser boundary contained zero direct requests to
`hazards.fema.gov`, `services.terrascope.be`, or other provider hosts.

| Evidence item | Result |
| --- | --- |
| AEGIS proxy requests | `113` across FEMA and ESA scenarios |
| AEGIS proxy responses | `95` (`83` image/png `200`; `12` provider-error JSON `502`) |
| Direct upstream browser requests | `0` |
| MapLibre source state | Unobserved / not loaded |
| MapLibre layer state | Unobserved / not loaded |
| Visible raster pixels | Unobserved |
| `map.render_ack` | Unobserved |
| Screenshots | Two failure-state captures in the rerun artifact directory |

The UI reported provider/source render failure after its supported recovery
attempts. This is a transport-boundary PARTIAL result: the provider URL was
not exposed to the browser renderer, but no successful provider raster image
was available to acknowledge.

## NASA GIBS matrix

All 12 advertised GIBS cases executed under the exact lane. Each assistant
run reached its configured execution limit before producing a raster route.
Every case therefore recorded `proxy_route_failure`, zero proxy requests,
zero direct-upstream requests, and no MapLibre source/layer or acknowledgement
evidence. The matrix harness passed; the T3-08 product gate remains `UNRUN`.

The local frontend regression and backend proxy tests prove generic contracts
only. They are not browser raster-render evidence and do not promote either
live gate.
