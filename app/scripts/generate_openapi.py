from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from fastapi import FastAPI


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def load_asgi_app(spec: str) -> FastAPI:
    module_name, separator, app_name = spec.partition(":")
    if not module_name or not separator or not app_name:
        raise ValueError("Expected --app in format '<module>:<attribute>'")

    module = importlib.import_module(module_name)
    application = getattr(module, app_name, None)
    if not isinstance(application, FastAPI):
        raise ValueError(
            f"App attribute '{app_name}' was not found as a FastAPI app "
            f"in module '{module_name}'"
        )
    return application


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate OpenAPI JSON for a FastAPI app."
    )
    parser.add_argument(
        "--app",
        default="server.app:app",
        help="ASGI app path, e.g. server.app:app",
    )
    parser.add_argument(
        "--output",
        default="app/shared/openapi.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    application = load_asgi_app(args.app)
    schema = application.openapi()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
