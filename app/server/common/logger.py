from __future__ import annotations

import logging
import logging.config
from datetime import datetime
from typing import Any

from server.common.paths import LOGS_PATH

# Generate timestamp for the log filename
###############################################################################
LOGS_PATH.mkdir(parents=True, exist_ok=True)
current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = LOGS_PATH / f"AEGIS_{current_timestamp}.log"

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
    "handlers": {
        "console": {
            "class": "server.common.logging_handlers.SafeStreamHandler",
            "level": "INFO",
            "formatter": "minimal",
        },
        "file": {
            "class": "logging.FileHandler",
            "level": "INFO",
            "formatter": "default",
            "filename": str(log_filename),
            "mode": "a",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "uvicorn.access": {
            "level": "WARNING",
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
        "level": "INFO",
        "handlers": ["console", "file"],
    },
}


# override logger configuration and load root logger
###############################################################################
logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger()
