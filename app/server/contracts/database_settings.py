from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.configurations.database_configuration import DatabaseConfiguration


###############################################################################
class DatabaseSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["sqlite"] = "sqlite"
    database_path: str = Field(min_length=1)
    sqlite_lock_timeout_seconds: int = Field(ge=1)

    # -------------------------------------------------------------------------
    @field_validator("database_path")
    @classmethod
    def require_nonblank_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("database_path must not be blank")
        return normalized

    # -------------------------------------------------------------------------
    def as_configuration(self) -> DatabaseConfiguration:
        return DatabaseConfiguration(
            backend=self.backend,
            database_path=self.database_path,
            sqlite_lock_timeout_seconds=self.sqlite_lock_timeout_seconds,
        )


###############################################################################
class DatabaseSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["sqlite"]
    database_path: str
    sqlite_lock_timeout_seconds: int
    active: bool = True


###############################################################################
class DatabaseConnectionTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    backend: Literal["sqlite"]
    database_path: str
    schema_status: Literal["ready", "upgradable", "empty"]
    message: str
