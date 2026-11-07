"""QA launcher: the AEGIS backend with OpenCode Go routed through the local fault proxy.

Run from app/: python backend_via_proxy.py <proxy_port>. Production code is not modified;
only the in-process base-URL table is patched before the app is imported.
"""
import os
import sys

import uvicorn

sys.path.insert(0, os.getcwd())

from server.services.llm import opencode_provider

opencode_provider.OPENCODE_BASE_URLS[opencode_provider.OPENCODE_GO_PROVIDER] = (
    f"http://127.0.0.1:{sys.argv[1]}"
)
uvicorn.run(
    "server.app:app", host="127.0.0.1", port=7059,
    ws_max_size=65536, ws_ping_interval=15, ws_ping_timeout=10,
)
