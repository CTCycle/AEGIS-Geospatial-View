from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPOSITORY_ROOT / "app"


###############################################################################
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


###############################################################################
def test_launcher_uses_confirmed_port_guard_and_process_aware_startup() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )

    def function_body(name: str) -> str:
        start = launcher.index(f"function {name}")
        end = launcher.find("\nfunction ", start + 1)
        return launcher[start:] if end < 0 else launcher[start:end]

    launch = function_body("Invoke-LaunchApplication")
    confirmation = function_body("Confirm-PortConflictTermination")
    conflicts = function_body("Resolve-LaunchPortConflicts")
    grouped_conflicts = function_body("Get-PortConflicts")
    health_wait = function_body("Wait-HttpHealth")

    assert "Stop-PortListeners" not in launch
    assert "taskkill.exe" not in launch
    assert launch.count("Resolve-LaunchPortConflicts") == 2
    assert "StartTimeUtcTicks" in confirmation
    assert "'unavailable'" in confirmation
    assert "no existing process was terminated" in confirmation
    assert confirmation.index("$unresolvedOwners") < confirmation.index("Read-Host")
    assert "Confirm-PortConflictTermination" in conflicts
    assert "HashSet[int]" in conflicts
    assert "Dictionary[int, object]" in grouped_conflicts
    assert "ContainsKey($processId)" in grouped_conflicts
    assert "importlib.import_module('server.app')" not in launch
    assert "[System.Diagnostics.Process]$Process" in health_wait
    assert "HasExited" in health_wait


###############################################################################
def test_launcher_separates_dependency_sync_from_build_state() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )
    package_json = json.loads(
        (APP_ROOT / "client" / "package.json").read_text(encoding="utf-8")
    )

    def function_body(name: str) -> str:
        start = launcher.index(f"function {name}")
        end = launcher.find("\nfunction ", start + 1)
        return launcher[start:] if end < 0 else launcher[start:end]

    launch = function_body("Invoke-LaunchApplication")
    install = function_body("Invoke-InstallOrUpdate")
    rebuild = function_body("Invoke-RebuildFrontend")

    assert "Sync-Dependencies -BuildFrontend $false" in launch
    assert "Ensure-FrontendBuildCurrent" in launch
    assert "-BuildFrontend $true" in install
    assert "Build-Frontend" in rebuild
    assert "ALWAYS_REBUILD" not in launcher
    assert "prebuild" in package_json["scripts"]
    assert "postbuild" in package_json["scripts"]
    assert "test:frontend-state" in package_json["scripts"]


###############################################################################
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


###############################################################################
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


###############################################################################
def test_all_tooling_resolves_disposable_state_under_canonical_cache_root() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )
    batch_runner = (APP_ROOT / "tests" / "run_tests.bat").read_text(
        encoding="utf-8"
    )
    server_config = tomllib.loads(
        (APP_ROOT / "server" / "pyproject.toml").read_text(encoding="utf-8")
    )
    angular_config = json.loads(
        (APP_ROOT / "client" / "angular.json").read_text(encoding="utf-8")
    )
    karma_config = (APP_ROOT / "client" / "karma.conf.cjs").read_text(
        encoding="utf-8"
    )
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml")
    )
    vscode_launch = (REPOSITORY_ROOT / ".vscode" / "launch.json").read_text(
        encoding="utf-8"
    )
    gitignore_text = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

    active_tooling_text = "\n".join(
        (
            launcher,
            batch_runner,
            karma_config,
            workflow_text,
            vscode_launch,
            gitignore_text,
        )
    ).replace("\\", "/")
    canonical_root = "runtimes/cache"
    assert canonical_root in active_tooling_text
    assert server_config["tool"]["pytest"]["ini_options"]["cache_dir"] == (
        "../../runtimes/cache/pytest"
    )
    assert server_config["tool"]["ruff"]["cache-dir"] == "../../runtimes/cache/ruff"
    assert angular_config["cli"]["cache"]["path"] == "../../runtimes/cache/angular"
    assert "../../runtimes/cache/coverage/aegis-client" in karma_config
    assert "enable-" + "cache:" not in workflow_text
    assert "cache:" + " npm" not in workflow_text
    assert "$ToolCacheDir" not in launcher
    assert "$LegacyCache" not in launcher
    assert "$LegacyUvCache" not in launcher
    assert "ValidateSet('Launch', 'ClearCache')" in launcher
    assert "Clear-ApplicationCache -SkipConfirmation -Strict" in launcher

    forbidden_fragments = (
        "/".join(("app", "tests", "cache")),
        "/".join(("assets", "cache")),
        "." + "pytest_cache",
        "." + "ruff_cache",
        "." + "tmp_pytest",
        "." + "angular",
    )
    for fragment in forbidden_fragments:
        assert fragment not in active_tooling_text

    dot_pytest_cache = "." + "pytest" + "_cache"
    dot_ruff_cache = "." + "ruff" + "_cache"
    dot_tmp_pytest = "." + "tmp" + "_pytest"
    obsolete_roots = (
        REPOSITORY_ROOT / "assets" / "cache",
        APP_ROOT / "tests" / "cache",
        APP_ROOT / "client" / ("." + "angular"),
        REPOSITORY_ROOT / dot_pytest_cache,
        REPOSITORY_ROOT / dot_ruff_cache,
        REPOSITORY_ROOT / dot_tmp_pytest,
        APP_ROOT / dot_pytest_cache,
        APP_ROOT / dot_ruff_cache,
        APP_ROOT / "server" / dot_pytest_cache,
        APP_ROOT / "server" / "app" / "tests" / "cache",
        APP_ROOT / "server" / (".pytest" + "-cache-gbif"),
        APP_ROOT / "server" / (".pytest" + "-cache-tiles"),
        APP_ROOT / "server" / (".pytest" + "-cache-typing"),
        APP_ROOT / (".pytest" + "-tmp-canonical-basemap"),
        APP_ROOT / (".pytest" + "-tmp-lane1-baseline"),
        APP_ROOT / (".pytest" + "-tmp-native-map"),
        APP_ROOT / (".pytest" + "-tmp-terrain-catalog"),
    )
    assert all(not path.exists() for path in obsolete_roots)
