"""
The BFF forwards only what the contract names (shape.py), on every route.

The strongest check is the leaky admin API: the stand-in's real answers, with extra
fields holding the canary string added to every object at every depth (the fields a
careless query would add: note text, titles, stacks, user agents). Nothing of it may
reach the browser, from any route, for any role.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Literal, Optional, Union

import httpx
import pytest
from pydantic import BaseModel, Field

from bff.app import contract as C
from bff.app.members import ROLES, Member
from bff.app.shape import prune

from .test_routes import ROUTES

CANARY = "CANARY-7f3a-DO-NOT-LEAK"
# What a leak looks like: words, the way notes, titles and stacks are written.
LEAK = f"{CANARY} the mitochondria is the powerhouse of the cell"


class Inner(BaseModel):
    a: int
    b: Optional[str] = None


class Outer(BaseModel):
    from_: date = Field(alias="from")
    inner: Inner
    many: list[Inner]
    maybe: Optional[Inner] = None
    tags: list[str]
    counts: dict[str, int]
    details: Optional[dict[str, Union[str, int, None, list[Union[str, int]]]]] = None
    kind: Literal["x", "y"] = "x"


def test_prune_keeps_declared_fields_at_every_depth(caplog):
    data = {
        "from": "2026-10-01",
        "inner": {"a": 1, "b": "ok", "note": CANARY},
        "many": [{"a": 2, "title": CANARY}, "junk", None, {"a": 3}],
        "maybe": None,
        "tags": ["x", {"nested": CANARY}, 5],
        "counts": {"password": 3, "google": {"bad": CANARY}},
        "details": {"ids": [1, 2], "fields": "status", "deep": {"text": CANARY}},
        "kind": "y",
        "encrypted_mentor_narrative": CANARY,
    }
    with caplog.at_level(logging.WARNING, logger="bff.shape"):
        out = prune(data, Outer)
    assert out == {
        "from": "2026-10-01",
        "inner": {"a": 1, "b": "ok"},
        "many": [{"a": 2}, None, {"a": 3}],
        "maybe": None,
        "tags": ["x"],  # an object and a number are not text
        "counts": {"password": 3, "google": None},
        "details": {"ids": [1, 2], "fields": "status", "deep": None},
        "kind": "y",
    }
    assert CANARY not in json.dumps(out)
    warning = caplog.records[-1].getMessage()
    assert "$.inner.note" in warning and "$.encrypted_mentor_narrative" in warning and "$.many[].title" in warning


def test_a_value_of_the_wrong_shape_becomes_null():
    assert prune({"a": {"text": CANARY}, "b": ["x"]}, Inner) == {"a": None, "b": None}
    assert prune(["not", "an", "object"], Inner) is None


async def test_a_correct_answer_comes_through_unchanged(harness):
    from bff.app.signing import signed_headers

    h = harness("owner")
    settings = h.app.state.settings
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=h.stub_app), base_url="http://admin-api:8001"
    ) as client:
        for path, model in (
            ("/admin/v1/users/5", C.UserDetail),
            ("/admin/v1/tickets/3", C.TicketDetail),
            ("/admin/v1/overview", C.Overview),
            ("/admin/v1/analytics/summary", C.AnalyticsSummary),
            ("/admin/v1/audit", C.AuditList),
        ):
            headers = signed_headers(
                service_token=settings.service_token,
                signing_key=settings.signing_key,
                method="GET",
                path_with_query=path,
                actor="dev@localhost",
                role="owner",
            )
            data = (await client.get(path, headers=headers)).json()
            assert prune(data, model) == data, path


class Leaky(httpx.AsyncBaseTransport):
    """The stand-in's answers, with canary fields added to every object."""

    def __init__(self, inner: httpx.AsyncBaseTransport):
        self.inner = inner

    @staticmethod
    def inject(value: Any) -> Any:
        if isinstance(value, dict):
            out = {k: Leaky.inject(v) for k, v in value.items()}
            out.update(
                {
                    "encrypted_mentor_narrative": LEAK,
                    "title": LEAK,
                    "stack": LEAK,
                    "user_agent": LEAK,
                    "data": {"stack": LEAK},
                    LEAK: 1,
                }
            )
            return out
        if isinstance(value, list):
            return [Leaky.inject(v) for v in value]
        return value

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        if "json" in response.headers.get("content-type", "") and body:
            return httpx.Response(response.status_code, json=self.inject(json.loads(body)))
        return httpx.Response(response.status_code, content=body, headers=response.headers)


ANALYTICS = [
    ("GET", "/bff/analytics/summary", None, "metrics.read"),
    ("GET", "/bff/analytics/errors", None, "metrics.read"),
    ("GET", "/bff/analytics/events?user_id=5", None, "activity.read"),
    ("GET", "/bff/settings/access-review", None, "settings.read"),
    ("GET", "/bff/settings/access-review.csv", None, "settings.read"),
    ("GET", "/bff/health", None, "users.read"),
]


@pytest.mark.parametrize("role", ROLES)
def test_nothing_the_contract_does_not_name_reaches_the_browser(role, harness):
    from devstub.app import create_stub

    from .conftest import KEY, TOKEN, fresh_store

    stub = create_stub(TOKEN, KEY, store=fresh_store())
    h = harness(role, transport=Leaky(httpx.ASGITransport(app=stub)))
    member = Member("dev@localhost", role)
    checked = 0
    for method, path, body, capability in ROUTES + ANALYTICS:
        r = h.get(path) if method == "GET" else h.send(method, path, body)
        assert CANARY not in r.text, (role, method, path)
        if member.can(capability):
            assert r.status_code == 200, (role, method, path, r.text[:200])
            checked += 1
    assert checked >= 10


def test_every_contract_model_forbids_extra_fields():
    """The stand-in builds its answers from these, and must not add fields either."""
    for name in dir(C):
        model = getattr(C, name)
        if isinstance(model, type) and issubclass(model, BaseModel) and model.__module__ == C.__name__:
            assert model.model_config.get("extra") == "forbid", name
