from __future__ import annotations

from pathlib import Path

from AEGIS.server.utils.variables import EnvironmentVariables


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

    monkeypatch.setattr("AEGIS.server.utils.variables.ENV_FILE_PATH", str(env_file))

    env_variables = EnvironmentVariables()

    assert env_variables.get("FASTAPI_HOST") == "127.0.0.1"
    assert env_variables.get("FASTAPI_PORT") == "6100"
    assert env_variables.get("UI_HOST") == "127.0.0.1"
    assert env_variables.get("UI_PORT") == "4980"
    assert env_variables.get("KERAS_BACKEND") == "tensorflow"
    assert env_variables.get("MPLBACKEND") == "Agg"
