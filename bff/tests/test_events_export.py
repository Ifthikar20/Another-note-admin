"""Live ticket events (5.5.3, 6.3.5) and the audit CSV export (6.4.9)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from bff.app.routes.audit import csv_cell
from bff.app.routes.events import SseParser, clean_event, relay, render

CANARY = "CANARY-7f3a-DO-NOT-LEAK"
GOOD = {"id": 7, "kind": "ticket.created", "ticket_id": 42, "created_at": "2026-10-15T12:00:00Z"}


def frame(event: str, data: object) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def test_the_parser_handles_any_chunking_and_line_ending():
    raw = (
        b": a comment\r\n"
        b'id: 7\r\nevent: ticket.created\r\ndata: {"a":\r\ndata: 1}\r\n\r\n'
        b"retry: 10\nevent: ticket.user_replied\ndata: {}\n\n"
        # A lone CR is a line end too, but one at the very end of what has arrived could be
        # the first half of a CRLF, so it waits for the next byte (here, a comment).
        b"data: plain\r\r: ping\n"
    )
    for size in (1, 2, 3, 7, len(raw)):
        parser = SseParser()
        events = []
        for i in range(0, len(raw), size):
            events += parser.feed(raw[i : i + size])
        assert events == [
            {"event": "ticket.created", "data": '{"a":\n1}'},
            {"event": "ticket.user_replied", "data": "{}"},
            {"event": "message", "data": "plain"},
        ], size


def test_a_line_without_end_is_bounded():
    parser = SseParser()
    with pytest.raises(ValueError):
        parser.feed(b"data: " + b"x" * 70_000)


def test_only_the_four_fields_of_a_known_event_go_out():
    leaky = {**GOOD, "subject": CANARY, "message": CANARY, "user": {"email": CANARY}}
    out = render({"event": "ticket.created", "data": json.dumps(leaky)})
    assert (
        out
        == b'id: 7\nevent: ticket.created\ndata: {"id":7,"kind":"ticket.created","ticket_id":42,"created_at":"2026-10-15T12:00:00Z"}\n\n'
    )


@pytest.mark.parametrize(
    "event",
    [
        {"event": "ticket.message", "data": json.dumps({**GOOD, "kind": "ticket.message"})},
        {"event": "ticket.user_replied", "data": json.dumps(GOOD)},  # name and kind disagree
        {"event": "ticket.created", "data": "{not json"},
        {"event": "ticket.created", "data": json.dumps([GOOD])},
        {"event": "ticket.created", "data": json.dumps({**GOOD, "id": "7"})},
        {"event": "ticket.created", "data": json.dumps({**GOOD, "id": True})},
        {"event": "ticket.created", "data": json.dumps({**GOOD, "ticket_id": 0})},
        {"event": "ticket.created", "data": json.dumps({**GOOD, "created_at": CANARY})},
        {"event": "message", "data": json.dumps(GOOD)},
    ],
)
def test_anything_else_is_dropped(event):
    assert render(event) is None


def test_clean_event():
    assert clean_event({**GOOD, "extra": 1}) == GOOD
    assert clean_event("ticket.created") is None


class Upstream(httpx.AsyncByteStream):
    def __init__(self, parts: list[tuple[float, bytes]]):
        self.parts = parts
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for delay, chunk in self.parts:
            await asyncio.sleep(delay)
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


async def collect(upstream: Upstream, heartbeat: float) -> list[bytes]:
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=upstream)
    return [chunk async for chunk in relay(response, heartbeat=heartbeat)]


async def test_heartbeats_while_quiet_and_events_whole():
    event = frame("ticket.created", GOOD)
    upstream = Upstream([(0.0, event[:10]), (0.35, event[10:])])
    out = await collect(upstream, heartbeat=0.1)
    assert out[0] == b"retry: 5000\n\n"
    assert b": heartbeat\n\n" in out
    # The heartbeat never lands inside an event: events go out whole.
    assert out[-1].startswith(b"id: 7\nevent: ticket.created\n")
    assert upstream.closed


async def test_the_upstream_is_closed_when_the_browser_leaves():
    upstream = Upstream([(0.0, frame("ticket.created", GOOD)), (10.0, b"")])
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=upstream)
    stream = relay(response, heartbeat=5)
    assert await stream.__anext__() == b"retry: 5000\n\n"
    assert (await stream.__anext__()).startswith(b"id: 7")
    await stream.aclose()
    assert upstream.closed


def test_the_stream_route_relays_through_the_allow_list(harness):
    body = (
        frame("ticket.created", {**GOOD, "subject": CANARY})
        + b": ping\n\n"
        + frame("ticket.secret", {**GOOD, "kind": "ticket.secret"})
        + frame("ticket.user_replied", {**GOOD, "id": 8, "kind": "ticket.user_replied"})
    )
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    h = harness("support", transport=httpx.MockTransport(handler))
    r = h.get("/bff/events/stream?after=6")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    assert CANARY not in r.text and "ticket.secret" not in r.text
    assert "id: 7\nevent: ticket.created" in r.text and "id: 8\nevent: ticket.user_replied" in r.text
    assert seen[0].url.raw_path == b"/admin/v1/events/stream?after=6"
    assert seen[0].headers["accept"] == "text/event-stream"


def test_the_stream_route_needs_support(harness):
    assert harness("viewer").get("/bff/events/stream").status_code == 403


def test_an_upstream_error_on_the_stream_is_an_error_not_a_stream(harness):
    h = harness(
        "support",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"error": {"code": "unauthorized", "message": "x"}})
        ),
    )
    r = h.get("/bff/events/stream")
    assert r.status_code == 502 and r.json()["error"]["code"] == "unavailable"


def test_recent_events_are_cleaned_too(harness):
    items = [{**GOOD, "subject": CANARY}, {**GOOD, "id": 9, "kind": "ticket.deleted"}, "junk"]
    h = harness(
        "support",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"items": items, "next_cursor": None})),
    )
    assert h.get("/bff/events?after=1").json() == {"items": [GOOD]}


def test_recent_events_from_the_stand_in(harness):
    h = harness("support")
    items = h.get("/bff/events?limit=5").json()["items"]
    assert len(items) == 5 and [e["id"] for e in items] == sorted(e["id"] for e in items)
    after = items[1]["id"]
    assert [e["id"] for e in h.get(f"/bff/events?after={after}&limit=100").json()["items"]][:3] == [
        after + 1,
        after + 2,
        after + 3,
    ]


# --- the audit export ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        ('=HYPERLINK("http://evil")', '\'=HYPERLINK("http://evil")'),
        ("+1", "'+1"),
        ("-2", "'-2"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tx", "'\tx"),
        ("plain", "plain"),
        (None, ""),
        (5, "5"),
        ({"b": 1, "a": ["x"]}, '{"a":["x"],"b":1}'),
    ],
)
def test_csv_cells_never_run_as_formulas(value, expected):
    assert csv_cell(value) == expected


def test_the_export_is_the_audit_log_as_csv(harness):
    h = harness("owner")
    h.stub.store.audit[-1].reason = "=cmd|' /C calc'!A0"
    r = h.get("/bff/audit/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.headers["content-disposition"].startswith('attachment; filename="anothernote-admin-audit-')
    assert r.headers["cache-control"] == "no-store"
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == [
        "at",
        "actor_email",
        "actor_role",
        "action",
        "target_type",
        "target_id",
        "reason",
        "request_id",
        "details",
    ]
    assert int(r.headers["x-export-rows"]) == len(rows) - 1 >= 80
    assert r.headers["x-export-truncated"] == "0"
    assert any(row[6] == "'=cmd|' /C calc'!A0" for row in rows[1:])


def test_the_export_is_capped(harness, monkeypatch):
    from bff.app.routes import audit

    monkeypatch.setattr(audit, "EXPORT_MAX_PAGES", 1)
    monkeypatch.setattr(audit, "EXPORT_PAGE", 10)
    r = harness("owner").get("/bff/audit/export.csv")
    assert r.headers["x-export-rows"] == "10" and r.headers["x-export-truncated"] == "1"
