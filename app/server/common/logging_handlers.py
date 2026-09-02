from __future__ import annotations

import logging


###############################################################################
class SafeStreamHandler(logging.StreamHandler):
    """Write console diagnostics without failing on a legacy code page."""

    # -------------------------------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            encoding = getattr(self.stream, "encoding", None)
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
