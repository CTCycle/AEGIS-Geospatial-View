from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

from AEGIS.server.utils.constants import ENV_FILE_PATH
from AEGIS.server.utils.logger import logger


@dataclass
class _EnvironmentState:
    lock: Lock = field(default_factory=Lock)
    loaded: bool = False


@lru_cache(maxsize=1)
def _environment_state() -> _EnvironmentState:
    return _EnvironmentState()


def ensure_environment_loaded(*, force: bool = False, env_path: str | Path | None = None) -> Path | None:
    state = _environment_state()
    path = Path(env_path) if env_path is not None else Path(ENV_FILE_PATH)

    with state.lock:
        if state.loaded and not force:
            return path if path.exists() else None

        if path.exists():
            load_dotenv(dotenv_path=path, override=True)
        else:
            logger.warning(".env file not found at: %s", path)

        state.loaded = True
        return path if path.exists() else None


def reset_environment_loader_for_tests() -> None:
    state = _environment_state()
    with state.lock:
        state.loaded = False
