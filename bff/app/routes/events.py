"""
Live ticket events: new tickets and replies from students, for the unread badge (5.5.3).

The admin API's outbox events are relayed to open admin tabs. Nothing is passed through
as it came: each event is parsed, must be one of the known kinds, and is rebuilt from
four fields (id, kind, ticket_id, created_at), so even a mistake upstream cannot put a
ticket's text on this stream. A comment line goes out every 20 seconds while nothing
else does, so proxies keep the connection open and a dead one is noticed.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any, Optional

import anyio
import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..deps import API, require
from ..members import Member

router = APIRouter()
logger = logging.getLogger("bff.events")

EVENT_KINDS = ("ticket.created", "ticket.user_replied")
HEARTBEAT_SECONDS = 20.0
MAX_LINE = 64 * 1024
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T[0-9:.]+(Z|[+-]\d{2}:\d{2})?$")

Reader = Annotated[Member, Depends(require("tickets.events"))]


def clean_event(data: Any) -> Optional[dict[str, Any]]:
    """The four allowed fields of an outbox event, or None if it is not one."""
    if not isinstance(data, dict):
        return None
    event_id, kind, ticket_id, created_at = (data.get(k) for k in ("id", "kind", "ticket_id", "created_at"))
    if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id < 1:
        return None
    if kind not in EVENT_KINDS:
        return None
    if not isinstance(ticket_id, int) or isinstance(ticket_id, bool) or ticket_id < 1:
        return None
    if not isinstance(created_at, str) or len(created_at) > 40 or not _ISO.match(created_at):
        return None
    return {"id": event_id, "kind": kind, "ticket_id": ticket_id, "created_at": created_at}


class SseParser:
    """Server-sent events, as the HTML standard defines them, fed in arbitrary chunks."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""
        self._reset()

    def _reset(self) -> None:
        self._data: list[str] = []
        self._event: Optional[str] = None

    def feed(self, chunk: bytes) -> list[dict[str, str]]:
        self._buffer += self._decoder.decode(chunk)
        events = []
        while True:
            cr, lf = self._buffer.find("\r"), self._buffer.find("\n")
            ends = [p for p in (cr, lf) if p != -1]
            if not ends:
                break
            end = min(ends)
            if self._buffer[end] == "\r":
                if end + 1 == len(self._buffer):
                    break  # a \r\n may be split across chunks
                step = 2 if self._buffer[end + 1] == "\n" else 1
            else:
                step = 1
            line, self._buffer = self._buffer[:end], self._buffer[end + step :]
            event = self._line(line)
            if event is not None:
                events.append(event)
        if len(self._buffer) > MAX_LINE:
            raise ValueError("an event stream line is too long")
        return events

    def _line(self, line: str) -> Optional[dict[str, str]]:
        if line == "":
            event = None
            if self._data:
                event = {"event": self._event or "message", "data": "\n".join(self._data)}
            self._reset()
            return event
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            self._data.append(value)
        elif field == "event":
            self._event = value
        return None


def render(event: dict[str, str]) -> Optional[bytes]:
    """An upstream event as it may go to the browser, or None to drop it."""
    if event.get("event") not in EVENT_KINDS:
        return None
    try:
        data = clean_event(json.loads(event.get("data", "")))
    except ValueError:
        return None
    if data is None or data["kind"] != event["event"]:
        return None
    payload = json.dumps(data, separators=(",", ":"))
    return f"id: {data['id']}\nevent: {data['kind']}\ndata: {payload}\n\n".encode()


async def relay(upstream: httpx.Response, heartbeat: float = HEARTBEAT_SECONDS) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=64)

    async def pump() -> None:
        try:
            async for chunk in upstream.aiter_bytes():
                await queue.put(chunk)
        except httpx.HTTPError:
            pass  # a read timeout or a dropped connection: end the stream, the browser reconnects
        finally:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    task = asyncio.create_task(pump())
    parser = SseParser()
    try:
        yield b"retry: 5000\n\n"
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except TimeoutError:
                yield b": heartbeat\n\n"
                continue
            if chunk is None:
                break
            try:
                events = parser.feed(chunk)
            except ValueError:
                logger.warning("dropping an admin event stream with an overlong line")
                break
            for event in events:
                out = render(event)
                if out is not None:
                    yield out
    finally:
        # Also reached when the browser goes away, inside a cancelled scope: shield the
        # clean-up so the upstream connection is always closed.
        task.cancel()
        with anyio.CancelScope(shield=True):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            await upstream.aclose()


@router.get("/events")
async def recent_events(
    request: Request,
    member: Reader,
    after: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> JSONResponse:
    data = await request.app.state.admin.call(
        "GET", f"{API}/events", actor=member, query={"after": after, "limit": limit}
    )
    items = data.get("items", []) if isinstance(data, dict) else []
    cleaned = [e for e in (clean_event(item) for item in items) if e is not None]
    return JSONResponse({"items": cleaned})


@router.get("/events/stream")
async def stream(
    request: Request, member: Reader, after: Annotated[Optional[int], Query(ge=0)] = None
) -> StreamingResponse:
    upstream = await request.app.state.admin.open_stream(f"{API}/events/stream", actor=member, query={"after": after})
    heartbeat = getattr(request.app.state, "heartbeat_seconds", HEARTBEAT_SECONDS)
    return StreamingResponse(
        relay(upstream, heartbeat),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )
