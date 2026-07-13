from __future__ import annotations

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    modules = {
        "AEGISDatabase": ("backend", "AEGISDatabase"),
        "get_database": ("backend", "get_database"),
        "DatabaseBackend": ("contracts", "DatabaseBackend"),
        "initialize_database": ("initializer", "initialize_database"),
        "initialize_sqlite_database": ("initializer", "initialize_sqlite_database"),
        "PostgresRepository": ("postgres", "PostgresRepository"),
        "SQLiteRepository": ("sqlite", "SQLiteRepository"),
    }
    if name not in modules:
        raise AttributeError(name)
    module_name, attribute = modules[name]
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute)
    globals()[name] = value
    return value


__all__ = [
    "AEGISDatabase",
    "DatabaseBackend",
    "get_database",
    "initialize_database",
    "initialize_sqlite_database",
    "PostgresRepository",
    "SQLiteRepository",
]
