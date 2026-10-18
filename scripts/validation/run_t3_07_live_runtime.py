"""T3-07 live raster validation runtime keeper.

Starts a disposable backend that already carries the exact configured
``opencode-go / deepseek-v4.1-flash`` lane, and keeps it alive for the
browser-authoritative FEMA/ESA raster evidence phase.

The credential is resolved in-process from the canonical database and is
never written to stdout, logs, or artifacts. The disposable runtime is
removed on exit unless ``--keep-runtime`` is supplied.

Usage:
    python scripts/validation/run_t3_07_live_runtime.py \
        --output-dir <assets/QA/.../T3-07> \
        [--backend-port 5079] [--keep-runtime]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPOSITORY_ROOT / "app"
SERVER_DIR = APP_DIR / "server"
CACHE_ROOT = REPOSITORY_ROOT / "runtimes" / "cache"
QA_ROOT = REPOSITORY_ROOT / "assets" / "QA"
PROTECTED_DATA = REPOSITORY_ROOT / "data"
PROTECTED_RESOURCES = APP_DIR / "resources"
PYTHON = SERVER_DIR / ".venv" / "Scripts" / "python.exe"

DEFAULT_BACKEND_PORT = 5079
READINESS_SECONDS = 40
PROBE_SECONDS = 180
LANE_PROVIDER = "opencode-go"
LANE_MODEL = "deepseek-v4.1-flash"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_opencode_key() -> str | None:
    """Resolve the opencode-go api key from the canonical database in-process."""

    sys.path.insert(0, str(APP_DIR))
    previous_data_dir = os.environ.get("AEGIS_DATA_DIR")
    os.environ["AEGIS_DATA_DIR"] = "data"
    try:
        from server.configurations import build_database_settings
        from server.repositories.database.sqlite import SQLiteRepository
        from server.repositories.credentials import CredentialRepository
        from server.repositories.credential_material import (
            CredentialEncryptionMaterialRepository,
        )
        from server.services.cryptography import CredentialEncryptionService
        from server.services.geospatial.credential_resolver import (
            GeospatialCredentialResolver,
        )

        database = SQLiteRepository(build_database_settings())
        resolver = GeospatialCredentialResolver(
            credentials_repo=CredentialRepository(database),
            crypto_service=CredentialEncryptionService(
                material_repo=CredentialEncryptionMaterialRepository(database)
            ),
        )
        return resolver.resolve(LANE_PROVIDER, label="api_key")
    finally:
        if previous_data_dir is None:
            os.environ.pop("AEGIS_DATA_DIR", None)
        else:
            os.environ["AEGIS_DATA_DIR"] = previous_data_dir


def _http_json(method: str, url: str, *, body: dict | None = None, timeout: int = 30) -> dict:
    import urllib.request

    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    parser.add_argument("--keep-runtime", action="store_true")
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    if not _is_within(output_dir, QA_ROOT) or output_dir == QA_ROOT.resolve():
        print("output-dir must be a child of assets\\QA.", file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.data_root:
        data_root = Path(args.data_root).resolve()
        if not _is_within(data_root, CACHE_ROOT) or data_root == CACHE_ROOT.resolve():
            print("data-root must be a child of runtimes\\cache.", file=sys.stderr)
            return 2
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        data_root = CACHE_ROOT / "test-runtime" / f"t3-07-live-{stamp}"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / ".aegis-t3-07-owned").write_text("", encoding="utf-8")

    backend_stdout = output_dir / "logs" / "backend.log"
    backend_stdout.parent.mkdir(parents=True, exist_ok=True)
    backend_stderr = output_dir / "logs" / "backend.stderr.log"
    result: dict = {
        "status": "BLOCKED",
        "reason": None,
        "tested_at": datetime.now(UTC).isoformat(),
        "provider": LANE_PROVIDER,
        "model": LANE_MODEL,
        "backend": f"http://127.0.0.1:{args.backend_port}",
        "data_root_isolated": True,
        "credential_present": False,
        "selected_provider": None,
        "selected_model": None,
        "probe": None,
    }

    key = _resolve_opencode_key()
    if not key:
        result["reason"] = "Canonical opencode-go credential is not available."
        _write_result(output_dir, result)
        return 3

    backend_env = dict(os.environ)
    backend_env["PYTHONPATH"] = str(APP_DIR)
    backend_env["AEGIS_DATA_DIR"] = str(data_root)
    backend_env["FASTAPI_HOST"] = "127.0.0.1"
    backend_env["FASTAPI_PORT"] = str(args.backend_port)
    # The backend serves the built client on the same origin, so the
    # realtime origin guard must accept that exact UI origin.
    backend_env["UI_HOST"] = "127.0.0.1"
    backend_env["UI_PORT"] = str(args.backend_port)
    backend_env.pop("AEGIS_T3_OPENCODE_GO_API_KEY", None)

    with backend_stdout.open("w", encoding="utf-8") as out, backend_stderr.open(
        "w", encoding="utf-8"
    ) as err:
        backend = subprocess.Popen(
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "server.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.backend_port),
            ],
            cwd=str(SERVER_DIR),
            env=backend_env,
            stdout=out,
            stderr=err,
        )

    api_base = f"http://127.0.0.1:{args.backend_port}"
    try:
        ready = False
        deadline = time.time() + READINESS_SECONDS
        while time.time() < deadline:
            if backend.poll() is not None:
                result["reason"] = f"Backend exited with code {backend.returncode}."
                return _finish(result, backend, output_dir, data_root, args)
            try:
                _http_json("GET", f"{api_base}/api/health", timeout=3)
                ready = True
                break
            except Exception:
                time.sleep(0.5)
        if not ready:
            result["reason"] = "Backend did not become ready."
            return _finish(result, backend, output_dir, data_root, args)

        _http_json(
            "PATCH",
            f"{api_base}/api/chat/settings",
            body={"credentials": {LANE_PROVIDER: {"api_key": key}}},
        )
        _http_json(
            "PATCH",
            f"{api_base}/api/chat/settings",
            body={
                "active_provider_mode": "cloud",
                "agent_model_provider": LANE_PROVIDER,
                "agent_model_name": LANE_MODEL,
            },
        )
        settings = _http_json("GET", f"{api_base}/api/chat/settings")
        credential_present = bool(
            settings.get("credentials", {}).get(LANE_PROVIDER, {}).get("api_key")
        )
        selected_provider = settings.get("agent_model_provider")
        selected_model = settings.get("agent_model_name")
        result["credential_present"] = credential_present
        result["selected_provider"] = selected_provider
        result["selected_model"] = selected_model
        if (
            not credential_present
            or selected_provider != LANE_PROVIDER
            or selected_model != LANE_MODEL
        ):
            result["reason"] = "Exact provider/model lane was not persisted."
            return _finish(result, backend, output_dir, data_root, args)

        probe = _http_json(
            "POST", f"{api_base}/api/chat/models/structured-probe", timeout=PROBE_SECONDS
        )
        result["probe"] = {
            "provider": probe.get("provider"),
            "model": probe.get("model"),
            "status": probe.get("status"),
            "parse_status": probe.get("parse_status"),
        }
        if probe.get("status") != "passed" or probe.get("parse_status") != "complete":
            result["reason"] = "Exact-lane structured probe did not pass."
            return _finish(result, backend, output_dir, data_root, args)

        result["status"] = "READY"
        result["reason"] = "Exact OpenCode Go lane ready on the isolated runtime."
        _write_result(output_dir, result)

        stop_marker = output_dir / "STOP"
        print("READY", flush=True)
        while not stop_marker.exists():
            if backend.poll() is not None:
                result["status"] = "BACKEND_EXITED"
                result["reason"] = f"Backend exited with code {backend.returncode}."
                _write_result(output_dir, result)
                return 4
            time.sleep(1)
        result["status"] = "STOPPED"
        result["reason"] = "Stop marker requested shutdown."
        return _finish(result, backend, output_dir, data_root, args)
    finally:
        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=15)
            except subprocess.TimeoutExpired:
                backend.kill()


def _finish(
    result: dict,
    backend: subprocess.Popen,
    output_dir: Path,
    data_root: Path,
    args: argparse.Namespace,
) -> int:
    _write_result(output_dir, result)
    if backend.poll() is None:
        backend.terminate()
        try:
            backend.wait(timeout=15)
        except subprocess.TimeoutExpired:
            backend.kill()
    if not args.keep_runtime and (data_root / ".aegis-t3-07-owned").exists():
        import shutil

        shutil.rmtree(data_root, ignore_errors=True)
    return 0 if result.get("status") in {"READY", "STOPPED"} else 1


def _write_result(output_dir: Path, result: dict) -> None:
    (output_dir / "live-runtime.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())