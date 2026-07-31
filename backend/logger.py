"""
Phase 5 — Observability & Logging Module
Provides structured JSON logging with request ID tracing across async contexts.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

# Context variable to hold current request ID across async calls
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(req_id: str) -> None:
    """Set request ID for current context."""
    request_id_ctx.set(req_id)


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return request_id_ctx.get()


class JSONLogFormatter(logging.Formatter):
    """Formatter that outputs JSON structured log records."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id() or "system",
        }

        # Attach exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Attach extra structured fields if passed via extra={}
        for key, val in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName"
            ):
                log_obj[key] = val

        return json.dumps(log_obj)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with structured JSON output."""
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter())
    root.addHandler(handler)

    # Quiet overly noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
