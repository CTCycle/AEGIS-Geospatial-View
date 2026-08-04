from __future__ import annotations

import os
from pathlib import Path

import pytest

from server.configurations.environment import (
    ensure_environment_loaded,
    reset_environment_bootstrap_for_tests,
)

###############################################################################
def test_runtime_env_is_loaded_from_dotenv(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FASTAPI_HOST=127.0.0.1",
                "FASTAPI_PORT=6100",
                "UI_HOST=127.0.0.1",
                "UI_PORT=4980",
                "KERAS_BACKEND=tensorflow",
                "MPLBACKEND=Agg",
            ]
        ),
        encoding="utf-8",
    )

    for key in (
        "FASTAPI_HOST",
        "FASTAPI_PORT",
        "UI_HOST",
        "UI_PORT",
        "KERAS_BACKEND",
        "MPLBACKEND",
    ):
        monkeypatch.delenv(key, raising=False)

    reset_environment_bootstrap_for_tests()
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    ensure_environment_loaded()

    assert os.getenv("FASTAPI_HOST") == "127.0.0.1"
    assert os.getenv("FASTAPI_PORT") == "6100"
    assert os.getenv("UI_HOST") == "127.0.0.1"
    assert os.getenv("UI_PORT") == "4980"
    assert os.getenv("KERAS_BACKEND") == "tensorflow"
    assert os.getenv("MPLBACKEND") == "Agg"

###############################################################################
def test_missing_runtime_env_is_created_from_example(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "settings" / ".env"
    example_file = tmp_path / "settings" / ".env.example"
    example_file.parent.mkdir()
    example_file.write_bytes(b"FASTAPI_PORT=6101\r\nEMBEDDED_DATABASE=true\r\n")

    monkeypatch.delenv("FASTAPI_PORT", raising=False)
    monkeypatch.delenv("EMBEDDED_DATABASE", raising=False)
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    monkeypatch.setattr(
        "server.configurations.environment.ENV_EXAMPLE_FILE_PATH", str(example_file)
    )
    reset_environment_bootstrap_for_tests()

    loaded_path = ensure_environment_loaded()

    assert loaded_path == env_file
    assert env_file.read_bytes() == example_file.read_bytes()
    assert os.getenv("FASTAPI_PORT") == "6101"
    assert os.getenv("EMBEDDED_DATABASE") == "true"

###############################################################################
def test_existing_runtime_env_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    existing = b"FASTAPI_PORT=6200\n"
    env_file.write_bytes(existing)
    example_file.write_bytes(b"FASTAPI_PORT=6300\n")

    monkeypatch.delenv("FASTAPI_PORT", raising=False)
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    monkeypatch.setattr(
        "server.configurations.environment.ENV_EXAMPLE_FILE_PATH", str(example_file)
    )
    reset_environment_bootstrap_for_tests()

    ensure_environment_loaded()

    assert env_file.read_bytes() == existing
    assert os.getenv("FASTAPI_PORT") == "6200"
