from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
from ctypes import wintypes
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PWSH = shutil.which("pwsh")


def _require_windows_powershell() -> str:
    if os.name != "nt" or PWSH is None:
        pytest.skip("Launcher cleanup integration requires Windows PowerShell 7.")
    return PWSH


def _write(root: Path, relative_path: str, contents: str = "fixture\n") -> Path:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")
    return target


def _make_repository_fixture(root: Path) -> dict[str, Path]:
    shutil.copy2(REPOSITORY_ROOT / "start_on_windows.ps1", root / "start_on_windows.ps1")
    _write(root, "settings/.env.example", "FASTAPI_PORT=8000\n")
    data_root = root.parent / "external-app-data"
    external_db = root.parent / "external-store" / "chosen.db"
    external_db.parent.mkdir(parents=True, exist_ok=True)
    external_db.write_text("persistent database sentinel", encoding="utf-8")
    database_journal = Path(f"{external_db}-journal")
    database_wal = Path(f"{external_db}-wal")
    database_shm = Path(f"{external_db}-shm")
    migration_lock = Path(f"{external_db}.migration.lock")
    migration_backup = external_db.with_name(
        f"{external_db.name}.migration-backup-fixture.db"
    )
    for companion in (
        database_journal,
        database_wal,
        database_shm,
        migration_lock,
        migration_backup,
    ):
        companion.write_text("sqlite companion sentinel", encoding="utf-8")
    recovery_db = root.parent / "external-store" / "previous-database.db"
    recovery_db.write_text("stale recovery-path sentinel", encoding="utf-8")
    _write(
        root,
        "settings/.env",
        f'AEGIS_DATA_DIR="{data_root}"\nFASTAPI_PORT=8000\n',
    )
    database_settings = {
        "schema_version": 1,
        "backend": "sqlite",
        "database_path": str(external_db),
        "sqlite_lock_timeout_seconds": 60,
    }
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "database-settings.json").write_text(
        json.dumps(database_settings), encoding="utf-8"
    )
    (data_root / "database-settings.json.bak").write_text(
        json.dumps({**database_settings, "database_path": str(recovery_db)}),
        encoding="utf-8",
    )
    paths = {
        "database": external_db,
        "database_journal": database_journal,
        "database_wal": database_wal,
        "database_shm": database_shm,
        "migration_lock": migration_lock,
        "migration_backup": migration_backup,
        "recovery_database": recovery_db,
        "database_settings": data_root / "database-settings.json",
        "database_settings_backup": data_root / "database-settings.json.bak",
        "env": root / "settings/.env",
        "upload": _write(root, "data/geospatial/uploads/kept.gpkg"),
        "vector": _write(root, "data/vectors/kept.bin"),
        "runtime_dataset": _write(data_root, "geospatial/overture/places.geojson", "{}\n"),
        "unknown_runtime_file": _write(data_root, "unrelated.keep"),
        "catalog": _write(root, "data/catalog/index.json", "{}\n"),
        "qa": _write(root, "assets/QA/report.md", "retained evidence\n"),
        "legacy_cache": _write(
            data_root,
            "geospatial/mobility_database_feeds_v2.csv",
            "generated cache\n",
        ),
        "external_catalog_override": _write(
            root.parent / "external-catalog-cache", "feeds.csv", "generated cache\n"
        ),
        "external_catalog_sibling": _write(
            root.parent / "external-catalog-cache", "keep.csv", "user file\n"
        ),
        "cache_file": _write(root, "runtimes/cache/uv/cache.bin"),
        "ruff_cache": _write(root, "app/tests/.ruff_cache/cache.bin"),
        "root_ruff_cache": _write(root, ".ruff_cache/cache.bin"),
        "pytest_cache": _write(root, "app/server/nested/.pytest_cache/cache.bin"),
        "bytecode": _write(root, "app/tests/__pycache__/module.pyc"),
        "validation_bytecode": _write(root, "scripts/validation/__pycache__/helper.pyc"),
        "app_runtime_cache": _write(root, "app/runtimes/cache/test-runtime/database.db"),
        "node_cache": _write(root, "app/client/node_modules/.cache/cache.bin"),
        "angular_cache": _write(root, "app/client/.angular/cache/cache.bin"),
        "frontend_build": _write(root, "app/client/dist/browser/index.html"),
        "app_log": _write(root, "data/logs/AEGIS_test.log"),
        "console_log": _write(root, "data/logs/backend-console.log"),
        "runtime": _write(root, "runtimes/python/python.exe"),
        "backend_venv": _write(root, "app/server/.venv/Scripts/python.exe"),
        "root_venv": _write(root, ".venv/Scripts/python.exe"),
        "frontend_dependency": _write(root, "app/client/node_modules/package.json", "{}\n"),
    }
    return paths


def _run_launcher(
    launcher: Path,
    working_directory: Path,
    action: str,
    *,
    what_if: bool = False,
    confirm_removal: bool = False,
    catalog_override: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("AEGIS_DATA_DIR", None)
    environment.pop("AEGIS_MOBILITY_DATABASE_CATALOG_PATH", None)
    environment.pop("AEGIS_CACHE_ROOT", None)
    if catalog_override is not None:
        environment["AEGIS_MOBILITY_DATABASE_CATALOG_PATH"] = str(catalog_override)
    arguments = [PWSH or "pwsh", "-NoLogo", "-NoProfile", "-File", str(launcher), "-Action", action]
    if what_if:
        arguments.append("-WhatIf")
    if confirm_removal:
        arguments.append("-ConfirmRemoval")
    return subprocess.run(
        arguments,
        cwd=working_directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_launcher_preview_cache_and_uninstall_preserve_user_data(tmp_path: Path) -> None:
    pwsh = _require_windows_powershell()
    assert pwsh == PWSH
    repository = tmp_path / "fixture-repository"
    repository.mkdir()
    outside = tmp_path / "other-working-directory"
    outside.mkdir()
    paths = _make_repository_fixture(repository)
    launcher = repository / "start_on_windows.ps1"

    preview = _run_launcher(
        launcher,
        outside,
        "ClearCache",
        what_if=True,
        catalog_override=paths["external_catalog_override"],
    )
    assert preview.returncode == 0, preview.stdout + preview.stderr
    for key in ("cache_file", "ruff_cache", "root_ruff_cache", "pytest_cache", "bytecode", "validation_bytecode", "app_runtime_cache", "node_cache", "angular_cache", "frontend_build", "legacy_cache"):
        assert str(paths[key]) in preview.stdout
        assert paths[key].exists()
    assert str(paths["external_catalog_override"]) in preview.stdout
    assert paths["external_catalog_sibling"].exists()

    cleared = _run_launcher(
        launcher,
        outside,
        "ClearCache",
        confirm_removal=True,
        catalog_override=paths["external_catalog_override"],
    )
    assert cleared.returncode == 0, cleared.stdout + cleared.stderr
    assert not paths["external_catalog_override"].exists()
    assert paths["external_catalog_sibling"].exists()
    repeated = _run_launcher(
        launcher,
        outside,
        "ClearCache",
        confirm_removal=True,
        catalog_override=paths["external_catalog_override"],
    )
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    for key in ("cache_file", "ruff_cache", "root_ruff_cache", "pytest_cache", "bytecode", "validation_bytecode", "app_runtime_cache", "node_cache", "angular_cache", "frontend_build", "legacy_cache"):
        assert not paths[key].exists()
    for key in (
        "database",
        "recovery_database",
        "database_settings",
        "database_settings_backup",
        "env",
        "upload",
        "vector",
        "runtime_dataset",
        "unknown_runtime_file",
        "catalog",
        "qa",
        "app_log",
        "console_log",
    ):
        assert paths[key].exists()

    log_preview = _run_launcher(launcher, outside, "RemoveLogs", what_if=True)
    assert log_preview.returncode == 0, log_preview.stdout + log_preview.stderr
    assert str(paths["app_log"]) in log_preview.stdout
    assert str(paths["console_log"]) in log_preview.stdout
    assert str(paths["database"]) not in log_preview.stdout
    removed_logs = _run_launcher(
        launcher, outside, "RemoveLogs", confirm_removal=True
    )
    assert removed_logs.returncode == 0, removed_logs.stdout + removed_logs.stderr
    assert not paths["app_log"].exists()
    assert not paths["console_log"].exists()

    paths["legacy_cache"].write_text("generated cache\n", encoding="utf-8")
    paths["external_catalog_override"].write_text(
        "generated cache\n", encoding="utf-8"
    )
    _write(repository, "data/logs/AEGIS_test.log")
    _write(repository, "data/logs/backend-console.log")
    _write(repository, "runtimes/uv/uv.exe")
    uninstall_runtime_cache = _write(
        repository, "app/runtimes/cache/test-runtime/database.db"
    )
    _write(repository, "app/client/dist/browser/index.html")
    uninstall_preview = _run_launcher(
        launcher,
        outside,
        "Uninstall",
        what_if=True,
        catalog_override=paths["external_catalog_override"],
    )
    assert uninstall_preview.returncode == 0, uninstall_preview.stdout + uninstall_preview.stderr
    assert str(paths["app_log"]) in uninstall_preview.stdout
    assert str(paths["database"]) not in uninstall_preview.stdout
    assert str(paths["database_settings"]) not in uninstall_preview.stdout
    assert str(uninstall_runtime_cache) in uninstall_preview.stdout
    assert str(paths["external_catalog_override"]) in uninstall_preview.stdout

    uninstalled = _run_launcher(
        launcher,
        outside,
        "Uninstall",
        confirm_removal=True,
        catalog_override=paths["external_catalog_override"],
    )
    assert uninstalled.returncode == 0, uninstalled.stdout + uninstalled.stderr
    for key in ("runtime", "backend_venv", "root_venv", "frontend_dependency", "frontend_build", "app_log", "console_log"):
        assert not paths[key].exists()
    assert not uninstall_runtime_cache.exists()
    assert not paths["legacy_cache"].exists()
    assert not paths["external_catalog_override"].exists()
    assert paths["external_catalog_sibling"].exists()
    for key in (
        "database",
        "recovery_database",
        "database_settings",
        "database_settings_backup",
        "env",
        "upload",
        "vector",
        "runtime_dataset",
        "unknown_runtime_file",
        "catalog",
        "qa",
    ):
        assert paths[key].exists()

    data_preview = _run_launcher(launcher, outside, "RemoveAllData", what_if=True)
    assert data_preview.returncode == 0, data_preview.stdout + data_preview.stderr
    assert str(paths["database"]) in data_preview.stdout
    assert str(paths["recovery_database"]) not in data_preview.stdout
    for key in ("database_journal", "database_wal", "database_shm", "migration_lock", "migration_backup"):
        assert str(paths[key]) in data_preview.stdout
    assert str(paths["upload"]) in data_preview.stdout
    assert str(paths["vector"]) in data_preview.stdout
    assert paths["database"].exists()

    removed_data = _run_launcher(launcher, outside, "RemoveAllData", confirm_removal=True)
    assert removed_data.returncode == 0, removed_data.stdout + removed_data.stderr
    for key in ("database", "database_journal", "database_wal", "database_shm", "migration_lock", "migration_backup", "database_settings", "upload", "vector", "runtime_dataset", "app_log", "console_log"):
        assert not paths[key].exists()
    assert paths["database_settings_backup"].exists() is False
    assert paths["recovery_database"].read_text(encoding="utf-8") == "stale recovery-path sentinel"
    for key in ("env", "catalog", "qa", "unknown_runtime_file"):
        assert paths[key].exists()


def test_launcher_cleanup_reports_locked_paths_and_does_not_follow_junctions(tmp_path: Path) -> None:
    _require_windows_powershell()
    repository = tmp_path / "fixture-repository"
    repository.mkdir()
    paths = _make_repository_fixture(repository)
    launcher = repository / "start_on_windows.ps1"
    working_directory = tmp_path

    locked_path = _write(repository, "runtimes/cache/uv/locked.bin")
    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(str(locked_path), 0x80000000, 0x00000001, None, 3, 0x80, None)
    invalid_handle = ctypes.c_void_p(-1).value
    assert ctypes.cast(handle, ctypes.c_void_p).value != invalid_handle
    try:
        blocked = _run_launcher(
            launcher, working_directory, "ClearCache", confirm_removal=True
        )
        assert blocked.returncode != 0
        assert "Failed to remove cleanup path" in blocked.stdout
        assert locked_path.exists()
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

    external = tmp_path / "outside-cache-target"
    external.mkdir()
    sentinel = _write(external, "keep.txt")
    junction = repository / "app/server/.pytest_cache/outside-link"
    junction.parent.mkdir(parents=True, exist_ok=True)
    link_result = subprocess.run(
        ["cmd.exe", "/c", "mklink", "/J", str(junction), str(external)],
        capture_output=True,
        text=True,
        check=False,
    )
    if link_result.returncode == 0:
        linked = _run_launcher(
            launcher, working_directory, "ClearCache", confirm_removal=True
        )
        assert linked.returncode != 0
        assert "Skipped reparse point" in linked.stdout
        assert sentinel.read_text(encoding="utf-8") == "fixture\n"
        junction.rmdir()

    restricted = _write(repository, "app/server/.ruff_cache/denied.bin")
    identity = subprocess.run(
        ["whoami.exe"], capture_output=True, text=True, check=False
    )
    icacls = shutil.which("icacls.exe")
    if identity.returncode == 0 and icacls is not None:
        denied = subprocess.run(
            [icacls, str(restricted.parent), "/deny", f"{identity.stdout.strip()}:(OI)(CI)(RD)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if denied.returncode == 0:
            try:
                permission_failure = _run_launcher(
                    launcher, working_directory, "ClearCache", confirm_removal=True
                )
                assert permission_failure.returncode != 0
                assert "incomplete:" in permission_failure.stdout
            finally:
                restored = subprocess.run(
                    [icacls, str(restricted.parent), "/remove:d", identity.stdout.strip()],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert restored.returncode == 0, restored.stdout + restored.stderr

    final = _run_launcher(
        launcher, working_directory, "ClearCache", confirm_removal=True
    )
    assert final.returncode == 0, final.stdout + final.stderr
    assert paths["database"].exists()
