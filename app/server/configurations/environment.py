from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

from server.common.logger import logger
from server.common.paths import ENV_FILE_PATH


@dataclass
class _EnvironmentState:
    lock: Lock = field(default_factory=Lock)
    bootstrapped: bool = False


@lru_cache(maxsize=1)
def _bootstrap_state() -> _EnvironmentState:
    return _EnvironmentState()


def ensure_environment_loaded(*, force: bool = False) -> Path | None:
    state = _bootstrap_state()
    path = Path(ENV_FILE_PATH)

    with state.lock:
        if state.bootstrapped and not force:
            return path if path.exists() else None

        if path.exists():
            load_dotenv(dotenv_path=path, override=True)
        else:
            logger.warning(".env file not found at: %s", path)

        state.bootstrapped = True
        return path if path.exists() else None


def reset_environment_bootstrap_for_tests() -> None:
    state = _bootstrap_state()
    with state.lock:
        state.bootstrapped = False
