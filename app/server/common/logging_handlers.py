from __future__ import annotations

import logging
from typing import TextIO


###############################################################################
class SafeStreamHandler(logging.StreamHandler[TextIO]):
    """Write console diagnostics without failing on a non-UTF-8 code page."""

    # -------------------------------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            encoding = self.stream.encoding
            if encoding:
                try:
                    message = message.encode(
                        encoding, errors="backslashreplace"
                    ).decode(encoding)
                except LookupError:
                    pass
            self.stream.write(message + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


###############################################################################
class AccessLogFilter(logging.Filter):
    """Keep successful requests at DEBUG and surface HTTP failures."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple) or len(record.args) != 5:
            return True
        try:
            status = int(record.args[4])
        except TypeError, ValueError:
            return True
        level = (
            logging.ERROR
            if status >= 500
            else logging.WARNING
            if status >= 400
            else logging.DEBUG
        )
        record.levelno = level
        record.levelname = logging.getLevelName(level)
        return True
