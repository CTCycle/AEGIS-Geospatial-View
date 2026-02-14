from __future__ import annotations

from typing import Any

__all__ = [
    "AEGISDatabase",
    "BACKEND_FACTORIES",
    "BackendFactory",
    "DatabaseBackend",
    "build_postgres_backend",
    "build_sqlite_backend",
    "database",
]


# -----------------------------------------------------------------------------
def __getattr__(name: str) -> Any:
    if name in __all__:
        from AEGIS.server.repositories.database import manager as manager_module

        return getattr(manager_module, name)
    raise AttributeError(
        f"module 'AEGIS.server.repositories.database' has no attribute {name!r}"
    )
