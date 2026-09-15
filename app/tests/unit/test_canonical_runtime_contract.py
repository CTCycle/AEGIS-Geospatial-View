from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPOSITORY_ROOT / "app"


def test_launcher_has_one_canonical_backend_entrypoint() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "$backendModule = 'server.app:app'" in launcher
    assert "$backendWorkingDirectory = $AppDir" in launcher
    assert "$env:PYTHONPATH = $AppDir" in launcher
    assert (
        "Start-Process -FilePath $venvPython -ArgumentList $backendArguments"
        in launcher
    )
    assert "app.server.app:app" not in launcher
    assert "Start-Process -FilePath 'cmd.exe'" not in launcher
    assert "/k" not in launcher


def test_old_import_root_is_rejected_when_only_app_is_on_pythonpath() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(APP_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; importlib.import_module('app.server.app')",
        ],
        cwd=APP_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0


def test_public_api_exposes_native_routes_without_shadow_or_legacy_routes() -> None:
    application = importlib.import_module("server.app").create_app()
    paths = {
        route.path
        for route in application.routes
        if isinstance(getattr(route, "path", None), str)
    }

    assert "/api/chat/turn" in paths
    assert "/api/chat/stream" in paths
    assert not any(
        marker in path.casefold()
        for path in paths
        for marker in ("/shadow", "/preview", "/legacy")
    )

    composition = (
        APP_ROOT / "server" / "services" / "chat" / "composition.py"
    ).read_text(encoding="utf-8").casefold()
    assert "nativeagentorchestrator" in composition
    assert "shadow" not in composition
    assert "legacy" not in composition
