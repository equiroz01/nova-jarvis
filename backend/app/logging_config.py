"""Structured logging with request correlation.

Default logging.basicConfig gives unstructured lines with no way to tie a log
back to the request/session that produced it — so a 2am failure means
reconstructing causality by hand. This stamps every line with the request_id
(and client_id) from contextvars, so `grep req=ab12cd34` reconstructs one whole
request, tool calls included.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from app.context import request_id_var, client_id_var

_FORMAT = "%(asctime)s %(levelname)s [req=%(request_id)s client=%(client_id)s] %(name)s: %(message)s"


class ContextFilter(logging.Filter):
    """Inject the current request_id / client_id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.client_id = client_id_var.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once. Honors NOVA_LOG_FILE for a rotating file sink
    (10MB x 5) in addition to stderr, so logs survive and don't fill the disk."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Replace any handlers basicConfig may have installed.
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(_FORMAT)
    ctx = ContextFilter()

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.addFilter(ctx)
    root.addHandler(stream)

    log_file = os.environ.get("NOVA_LOG_FILE")
    if log_file:
        try:
            fileh = RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            fileh.setFormatter(fmt)
            fileh.addFilter(ctx)
            root.addHandler(fileh)
        except Exception:
            root.warning("Could not open NOVA_LOG_FILE=%s; logging to stderr only",
                         log_file, exc_info=True)
