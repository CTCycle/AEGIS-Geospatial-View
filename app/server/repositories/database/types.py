from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON
from sqlalchemy.engine import Dialect
from sqlalchemy.types import DateTime, TypeDecorator

###############################################################################
class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC consistently and return timezone-aware values on every backend."""

    impl = DateTime
    cache_ok = True

    # -------------------------------------------------------------------------
    def load_dialect_impl(self, dialect: Dialect):
        return dialect.type_descriptor(DateTime(timezone=dialect.name == "postgresql"))

    # -------------------------------------------------------------------------
    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        value = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return value if dialect.name == "postgresql" else value.replace(tzinfo=None)

    # -------------------------------------------------------------------------
    def process_result_value(self, value: datetime | None, dialect: Dialect):
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)

###############################################################################
class PortableJSON(TypeDecorator[object]):
    """Use JSON semantics in Python and JSON/JSONB-compatible storage."""

    impl = JSON
    cache_ok = True
