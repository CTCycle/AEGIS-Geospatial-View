from __future__ import annotations

import logging
import re
import traceback
from typing import TextIO

_SECRET_ASSIGNMENT = re.compile(
    r"((?:api[_-]?key|access[_-]?token|auth(?:orization)?|credential|password|"
    r"secret|token|key)[\"']?\s*[=:]\s*[\"']?)(?:bearer\s+)?[^\s&\"',;)}\]]+",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
_MAX_CONTEXT_VALUE_CHARS = 200


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
            status = int(str(record.args[4]))
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


###############################################################################
def redact_secrets(text: str) -> str:
    """Mask credential-like assignments and bearer tokens in diagnostic text."""

    return _BEARER.sub(r"\1<redacted>", _SECRET_ASSIGNMENT.sub(r"\1<redacted>", text))


###############################################################################
def log_unexpected_failure(
    logger: logging.Logger,
    exc: BaseException,
    *,
    stage: str,
    level: int = logging.ERROR,
    **context: object,
) -> None:
    """Keep server-side evidence for a failure the caller reports generically.

    The record carries the execution stage, caller context (run, tool, call
    identifiers), exception type and a redacted traceback; payloads are never
    included.
    """

    fields = " ".join(
        f"{key}={_context_value(value)}"
        for key, value in context.items()
        if value is not None
    )
    trace = redact_secrets("".join(traceback.format_exception(exc)).rstrip())
    logger.log(
        level,
        "unexpected_failure stage=%s %s exception_type=%s\n%s",
        stage, fields, type(exc).__name__, trace,
    )


###############################################################################
def _context_value(value: object) -> str:
    # Context values may echo caller input: keep each one on a single line,
    # bounded and free of credentials.
    text = _CONTROL_CHARS.sub(" ", redact_secrets(str(value))).strip()
    if len(text) > _MAX_CONTEXT_VALUE_CHARS:
        return text[:_MAX_CONTEXT_VALUE_CHARS] + "..."
    return text
