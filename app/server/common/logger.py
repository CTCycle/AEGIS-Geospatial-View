from __future__ import annotations

import logging
import logging.config
import os
from datetime import datetime
from typing import Any

from dotenv import dotenv_values

from server.common.paths import ENV_EXAMPLE_FILE_PATH, ENV_FILE_PATH, LOGS_PATH

# Generate timestamp for the log filename
###############################################################################
LOGS_PATH.mkdir(parents=True, exist_ok=True)
current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = LOGS_PATH / f"AEGIS_{current_timestamp}.log"

# Read the setting early, before application startup imports emit diagnostics.
_environment_path = ENV_FILE_PATH if ENV_FILE_PATH.is_file() else ENV_EXAMPLE_FILE_PATH
_log_level = os.environ.get(
    "AEGIS_LOG_LEVEL", dotenv_values(_environment_path).get("AEGIS_LOG_LEVEL") or "INFO"
).upper()
if _log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
    _log_level = "INFO"

# Define logger configuration
###############################################################################
LOG_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%d-%m-%Y %H:%M:%S",
        },
        "minimal": {
            "format": "[%(levelname)s] %(message)s",
        },
    },
    "filters": {"access": {"()": "server.common.logging_handlers.AccessLogFilter"}},
    "handlers": {
        "console": {
            "class": "server.common.logging_handlers.SafeStreamHandler",
            "level": _log_level,
            "formatter": "minimal",
        },
        "file": {
            "class": "logging.FileHandler",
            "level": _log_level,
            "formatter": "default",
            "filename": str(log_filename),
            "mode": "a",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "uvicorn": {
            "level": _log_level,
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": "DEBUG",
            "filters": ["access"],
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "matplotlib": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "openai": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "openai._base_client": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "httpx": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "httpcore": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "asyncio": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "alembic.autogenerate": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "alembic.runtime.plugins": {
            "level": "WARNING",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
    "root": {
        "level": _log_level,
        "handlers": ["console", "file"],
    },
}


# override logger configuration and load root logger
###############################################################################
logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger()
