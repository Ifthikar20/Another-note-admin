"""
Log lines, and the request id that ties them to the admin API's audit log.

Format: text for people (the default, and development), or one JSON object per line for
CloudWatch Logs Insights (LOG_FORMAT=json, which the image sets). Either way a line
never holds a query string, a request body or a token.

Request ids: every /bff request gets one. It is the X-Request-Id of the response, it is
on the request's log line, and it is the X-Admin-Request-Id of the first admin API call
made for that request, which the admin API stores in the audit row it writes. So an
audit row leads to the log line that caused it, and a reference quoted from an error
message leads to both. A request that makes several admin API calls (the audit export)
gives the others fresh ids, listed on its log line: the admin API refuses an id it has
already seen.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Optional

# What a log line may carry beyond its message, in this order. Nothing else is written.
FIELDS = ("method", "path", "status", "duration_ms", "actor", "role", "request_id", "admin_request_ids", "reason")
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class RequestTrace:
    """The ids of one /bff request."""

    __slots__ = ("admin_ids", "request_id")

    def __init__(self) -> None:
        self.request_id = str(uuid.uuid4())
        self.admin_ids: list[str] = []

    def next_admin_id(self) -> str:
        """The id for the next admin API call: this request's own first, then fresh ones."""
        rid = str(uuid.uuid4()) if self.admin_ids else self.request_id
        self.admin_ids.append(rid)
        return rid

    def extra_admin_ids(self) -> Optional[list[str]]:
        return self.admin_ids[1:] or None


_trace: contextvars.ContextVar[Optional[RequestTrace]] = contextvars.ContextVar("bff_request_trace", default=None)


def current_trace() -> Optional[RequestTrace]:
    return _trace.get()


def begin_trace() -> tuple[RequestTrace, contextvars.Token[Optional[RequestTrace]]]:
    trace = RequestTrace()
    return trace, _trace.set(trace)


def end_trace(token: contextvars.Token[Optional[RequestTrace]]) -> None:
    _trace.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=str)


class _Handler(logging.StreamHandler):  # type: ignore[type-arg]
    """Marks the handler this module installed, so configuring twice changes nothing."""


def configure(env: Mapping[str, str]) -> None:
    """Send every log record (uvicorn's included) to stderr in the chosen format."""
    root = logging.getLogger()
    if any(isinstance(h, _Handler) for h in root.handlers):
        return
    handler = _Handler(sys.stderr)
    if (env.get("LOG_FORMAT") or "text").strip().lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT))
    root.addHandler(handler)
    root.setLevel((env.get("LOG_LEVEL") or "INFO").strip().upper())
