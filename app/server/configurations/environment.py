from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv

from server.common.logger import logger
from server.common.paths import ENV_EXAMPLE_FILE_PATH, ENV_FILE_PATH

###############################################################################
@dataclass
class _EnvironmentState:
    lock: Lock = field(default_factory=Lock)
    bootstrapped: bool = False

###############################################################################
@lru_cache(maxsize=1)
def _bootstrap_state() -> _EnvironmentState:
    return _EnvironmentState()

###############################################################################
def _create_environment_file(path: Path) -> None:
    template_path = Path(ENV_EXAMPLE_FILE_PATH)
    if not template_path.is_file():
        raise FileNotFoundError(f"Missing environment template: {template_path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as environment_file:
            environment_file.write(template_path.read_bytes())
    except FileExistsError:
        return

    logger.info("Created %s from %s.", path, template_path)

###############################################################################
def ensure_environment_loaded(*, force: bool = False) -> Path | None:
    state = _bootstrap_state()
    path = Path(ENV_FILE_PATH)

    with state.lock:
        if state.bootstrapped and not force:
            return path if path.exists() else None

        if not path.exists():
            _create_environment_file(path)
        load_dotenv(dotenv_path=path, override=True)

        state.bootstrapped = True
        return path

###############################################################################
def reset_environment_bootstrap_for_tests() -> None:
    state = _bootstrap_state()
    with state.lock:
        state.bootstrapped = False
