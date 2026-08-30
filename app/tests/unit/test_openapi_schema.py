from __future__ import annotations

import json
from pathlib import Path

from server.app import app


SHARED_OPENAPI_PATH = Path(__file__).resolve().parents[2] / "shared" / "openapi.json"


###############################################################################
def test_shared_openapi_schema_matches_runtime() -> None:
    shared_schema = json.loads(SHARED_OPENAPI_PATH.read_text(encoding="utf-8"))

    assert shared_schema == app.openapi()
