from __future__ import annotations

import logging

from server.common.logger import LOG_CONFIG
from server.common.logging_handlers import AccessLogFilter, SafeStreamHandler


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
    assert LOG_CONFIG["handlers"]["console"]["level"] == LOG_CONFIG["root"]["level"]
    assert LOG_CONFIG["handlers"]["file"]["level"] == LOG_CONFIG["root"]["level"]
    assert LOG_CONFIG["handlers"]["file"]["encoding"] == "utf-8"
    assert LOG_CONFIG["loggers"]["openai"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["httpx"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["httpcore"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["alembic.autogenerate"]["level"] == "WARNING"
    assert LOG_CONFIG["loggers"]["alembic.runtime.plugins"]["level"] == "WARNING"


###############################################################################
def test_access_logs_classify_success_and_failures() -> None:
    access_filter = AccessLogFilter()
    for status, level in [
        (200, logging.DEBUG),
        (404, logging.WARNING),
        (503, logging.ERROR),
    ]:
        record = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1", "GET", "/api/health", "1.1", status),
            None,
        )
        assert access_filter.filter(record)
        assert record.levelno == level
        assert record.levelname == logging.getLevelName(level)


###############################################################################
def test_access_filter_preserves_unrecognized_records() -> None:
    record = logging.LogRecord(
        "uvicorn.access", logging.WARNING, __file__, 1, "unexpected", (), None
    )
    assert AccessLogFilter().filter(record)
    assert record.levelno == logging.WARNING
