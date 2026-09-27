"""
The stand-in admin API on its own: it is the reference for the real one (phase 2), so it
must enforce the role table itself, audit every request, and never pass on what the
privacy contract keeps back.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from bff.app.admin_client import build_path
from bff.app.signing import signed_headers
from devstub.app import create_stub
from devstub.data import CANARY, Store

TOKEN, KEY = "stub-token-" + "0" * 30, "stub-key-" + "1" * 30
NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def seeded() -> Store:
    return Store(now=NOW)


@pytest.fixture
def call(seeded):
    import pickle

    app = create_stub(TOKEN, KEY, store=pickle.loads(pickle.dumps(seeded)))

    async def go(method: str, path: str, role: str = "owner", query=None, body=None) -> httpx.Response:
        target = build_path(path, query)
        content = json.dumps(body).encode() if body is not None else b""
        headers = signed_headers(
            service_token=TOKEN,
            signing_key=KEY,
            method=method,
            path_with_query=target,
            actor="x@anothernote.app",
            role=role,
            body=content,
        )
        if content:
            headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://admin-api:8001"
        ) as client:
            return await client.request(method, target, content=content or None, headers=headers)

    go.app = app  # type: ignore[attr-defined]
    return go


# (method, path, body, roles allowed) per 5.8.4
TABLE = [
    ("GET", "/admin/v1/overview", None, {"owner", "support", "analyst", "viewer"}),
    ("POST", "/admin/v1/users/5/reveal-email", {"reason": "Replying to AN-0003"}, {"owner", "support"}),
    ("POST", "/admin/v1/users/5/sign-out-everywhere", {"reason": "Lost their phone"}, {"owner", "support"}),
    ("POST", "/admin/v1/users/5/deactivate", {"reason": "Asked us to close it"}, {"owner"}),
    ("GET", "/admin/v1/users/5/auth-events", None, {"owner", "support"}),
    ("GET", "/admin/v1/users/5/tickets", None, {"owner", "support"}),
    ("PUT", "/admin/v1/users/5/plan", {"plan_id": "plus", "status": "active", "note": "Goodwill"}, {"owner"}),
    ("POST", "/admin/v1/plans", {"id": "pro", "name": "Pro"}, {"owner"}),
    ("GET", "/admin/v1/tickets", None, {"owner", "support", "viewer"}),
    ("POST", "/admin/v1/tickets/3/messages", {"body": "Hello"}, {"owner", "support"}),
    ("GET", "/admin/v1/events", None, {"owner", "support"}),
    ("GET", "/admin/v1/security/summary", None, {"owner", "support"}),
    ("GET", "/admin/v1/analytics/events", None, {"owner", "support"}),
    ("GET", "/admin/v1/analytics/errors", None, {"owner", "support", "analyst", "viewer"}),
    ("GET", "/admin/v1/audit", None, {"owner"}),
    ("GET", "/admin/v1/usage/prices", None, {"owner"}),
]


@pytest.mark.parametrize("method,path,body,allowed", TABLE)
async def test_the_stand_in_enforces_the_role_table_itself(method, path, body, allowed, call):
    for role in ("owner", "support", "analyst", "viewer"):
        r = await call(method, path, role, body=body)
        assert (r.status_code == 200) is (role in allowed), (role, method, path, r.status_code, r.text[:120])
        if role not in allowed:
            assert r.json() == {"error": {"code": "forbidden", "message": "Your role cannot do this."}}


async def test_every_request_writes_one_audit_row_failures_included(call):
    store = call.app.state.stub.store
    before = len(store.audit)
    await call("GET", "/admin/v1/users/5", "viewer")
    await call("POST", "/admin/v1/users/5/reveal-email", "viewer", body={"reason": "Curious about them"})
    await call("POST", "/admin/v1/users/5/reveal-email", "support", body={"reason": "no"})
    await call("GET", "/admin/v1/users/99999", "viewer")
    rows = store.audit[before:]
    assert [(r.action, r.target_id, (r.details or {}).get("status")) for r in rows] == [
        ("view.user", "5", None),
        ("user.reveal_email", "5", 403),
        ("user.reveal_email", "5", 400),
        ("view.user", "99999", 404),
    ]
    assert rows[1].reason == "Curious about them"


async def test_privileged_actions_need_a_reason(call):
    for path in ("reveal-email", "sign-out-everywhere", "deactivate"):
        r = await call("POST", f"/admin/v1/users/5/{path}", body={"reason": "   "})
        assert r.status_code == 400 and r.json()["error"]["message"] == "a reason is required"


async def test_analytics_never_shows_stacks_agents_or_other_tags(call, seeded):
    assert any(CANARY in json.dumps(e.data) for e in seeded.events if e.data)
    assert any("gclid" in (e.tags or {}) or "ref" in (e.tags or {}) for e in seeded.events)
    for path, query in (
        ("/admin/v1/analytics/events", {"kind": "error", "limit": 100}),
        ("/admin/v1/analytics/events", {"limit": 100}),
        ("/admin/v1/analytics/errors", {"limit": 100}),
        ("/admin/v1/analytics/summary", None),
    ):
        r = await call("GET", path, "owner", query=query)
        assert r.status_code == 200
        for secret in (CANARY, "Mozilla/5.0", "gclid", "twclid", "tester-priya", "stack"):
            assert secret not in r.text, (path, secret)


async def test_error_names_are_at_most_160_characters(call):
    store = call.app.state.stub.store
    store.events[-1].kind, store.events[-1].name = "error", "E" * 400
    r = await call("GET", "/admin/v1/analytics/events", query={"kind": "error", "limit": 1})
    assert len(r.json()["items"][0]["name"]) == 160


async def test_the_live_generator_makes_tickets_and_events(seeded):
    import pickle

    app = create_stub(TOKEN, KEY, store=pickle.loads(pickle.dumps(seeded)), live_events=True, live_interval=0.01)
    stub = app.state.stub
    tickets, events = len(stub.store.tickets), len(stub.store.outbox)
    queue: asyncio.Queue = asyncio.Queue()
    stub.subscribers.add(queue)
    task = asyncio.create_task(stub.live())
    await asyncio.sleep(0.2)
    task.cancel()
    assert len(stub.store.outbox) > events and not queue.empty()
    assert len(stub.store.tickets) >= tickets
    event = queue.get_nowait()
    assert event.kind in ("ticket.created", "ticket.user_replied") and event.ticket_id in stub.store.tickets
