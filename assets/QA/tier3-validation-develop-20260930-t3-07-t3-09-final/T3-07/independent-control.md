# Independent FEMA control

The external web control attempted the FEMA NFHL service metadata endpoint and
layer `28` metadata endpoint from the independent web network. Both were
reported as inaccessible by that network, so this does not prove FEMA is
healthy or unhealthy upstream and does not change the same-host diagnosis.

The authoritative same-host matrix remains: DNS and TCP 443 succeed, while
native curl, fresh `httpx`, AEGIS pooled HTTP, REST metadata/query/export, and
WMS fail before HTTP status, content type, or body. No FEMA vector fallback was
implemented because the query path is not reachable from the target host.
