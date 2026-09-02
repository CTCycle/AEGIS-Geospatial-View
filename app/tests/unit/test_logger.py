from __future__ import annotations

import logging

from server.common.logger import LOG_CONFIG
from server.common.logging_handlers import SafeStreamHandler


###############################################################################
class _LegacyCodePageStream:
    encoding = "cp1252"

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.values: list[str] = []

    # -------------------------------------------------------------------------
    def write(self, value: str) -> int:
        value.encode(self.encoding)
        self.values.append(value)
        return len(value)

    # -------------------------------------------------------------------------
    def flush(self) -> None:
        return None


###############################################################################
def test_console_handler_escapes_unrepresentable_units_without_logging_error() -> None:
    stream = _LegacyCodePageStream()
    handler = SafeStreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))

    handler.emit(
        logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="PM2.5 μg/m³",
            args=(),
            exc_info=None,
        )
    )

    assert stream.values == ["PM2.5 \\u03bcg/m³\n"]


###############################################################################
def test_normal_logging_is_concise_and_file_output_is_utf8() -> None:
    assert LOG_CONFIG["handlers"]["console"]["level"] == "INFO"
    assert LOG_CONFIG["handlers"]["file"]["level"] == "INFO"
    assert LOG_CONFIG["handlers"]["file"]["encoding"] == "utf-8"
    assert LOG_CONFIG["root"]["level"] == "INFO"
    assert LOG_CONFIG["loggers"]["openai"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["httpx"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["httpcore"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["alembic.autogenerate"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["alembic.runtime.plugins"]["level"] == "WARNING"
