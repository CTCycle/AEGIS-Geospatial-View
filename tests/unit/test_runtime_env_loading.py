from __future__ import annotations

import os
from pathlib import Path

from AEGIS.server.configurations.environment import (
    ensure_environment_loaded,
    reset_environment_loader_for_tests,
)


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

    reset_environment_loader_for_tests()
    ensure_environment_loaded(env_path=env_file)

    assert os.getenv("FASTAPI_HOST") == "127.0.0.1"
    assert os.getenv("FASTAPI_PORT") == "6100"
    assert os.getenv("UI_HOST") == "127.0.0.1"
    assert os.getenv("UI_PORT") == "4980"
    assert os.getenv("KERAS_BACKEND") == "tensorflow"
    assert os.getenv("MPLBACKEND") == "Agg"
