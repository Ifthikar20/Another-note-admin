"""
The route allow-list: every route the UI uses, the role table enforced route by route
(5.8.3, 5.8.4), what is validated before anything is forwarded, and how admin API
failures reach the browser.
"""

from __future__ import annotations

import re

import httpx
import pytest

from bff.app.members import ROLES, Member

REASON = {"reason": "Asked by the person in AN-0003"}
ASSIGN = {"plan_id": "plus", "status": "active", "note": "Support goodwill"}

# (method, path, body, capability): every /bff route there is.
ROUTES = [
    ("GET", "/bff/overview?from=2026-10-01&to=2026-10-15", None, "metrics.read"),
    ("GET", "/bff/metrics/active-users", None, "metrics.read"),
    ("GET", "/bff/metrics/sign-ins", None, "metrics.read"),
    ("GET", "/bff/metrics/online-now", None, "metrics.read"),
    ("GET", "/bff/users?kind=standard&sort=last_seen", None, "users.read"),
    ("GET", "/bff/users/5", None, "users.read"),
    ("POST", "/bff/users/5/reveal-email", REASON, "users.reveal_email"),
    ("GET", "/bff/users/5/sessions", None, "users.read"),
    ("POST", "/bff/users/5/sign-out-everywhere", REASON, "users.sign_out"),
    ("POST", "/bff/users/5/deactivate", REASON, "users.set_active"),
    ("POST", "/bff/users/5/reactivate", REASON, "users.set_active"),
    ("GET", "/bff/users/5/usage?group=feature", None, "metrics.read"),
    ("GET", "/bff/users/5/auth-events", None, "users.auth_events"),
    ("GET", "/bff/users/5/tickets", None, "users.tickets"),
    ("GET", "/bff/users/5/plan", None, "users.read"),
    ("PUT", "/bff/users/5/plan", ASSIGN, "plans.write"),
    ("GET", "/bff/usage/summary?group=model", None, "metrics.read"),
    ("GET", "/bff/usage/top-users?metric=tokens&limit=5", None, "metrics.read"),
    ("GET", "/bff/usage/anomalies?date=2026-10-14", None, "metrics.read"),
    ("GET", "/bff/plans", None, "plans.read"),
    ("POST", "/bff/plans", {"id": "pro", "name": "Pro"}, "plans.write"),
    ("PATCH", "/bff/plans/plus", {"description": "For one person who studies a lot."}, "plans.write"),
    ("GET", "/bff/orgs?q=lincoln", None, "orgs.read"),
    ("GET", "/bff/orgs/1", None, "orgs.read"),
    ("PUT", "/bff/orgs/4/plan", ASSIGN, "plans.write"),
    ("GET", "/bff/tickets?status=open", None, "tickets.read"),
    ("GET", "/bff/tickets/3", None, "tickets.read"),
    ("POST", "/bff/tickets/3/messages", {"body": "Thanks, looking into it.", "internal": False}, "tickets.write"),
    ("PATCH", "/bff/tickets/3", {"priority": "high"}, "tickets.write"),
    ("GET", "/bff/events?after=0", None, "tickets.events"),
    ("GET", "/bff/security/summary", None, "security.read"),
    ("GET", "/bff/security/auth-events?kind=sign_in_failed", None, "security.read"),
    ("GET", "/bff/audit?action=view.user", None, "audit.read"),
    ("GET", "/bff/audit/export.csv", None, "audit.read"),
    ("GET", "/bff/settings/members", None, "settings.read"),
    ("GET", "/bff/settings/prices", None, "settings.read"),
    ("GET", "/bff/settings/access-review", None, "settings.read"),
    ("GET", "/bff/settings/access-review.csv", None, "settings.read"),
    ("GET", "/bff/analytics/summary?from=2026-10-01&to=2026-10-15", None, "metrics.read"),
    ("GET", "/bff/analytics/errors?q=api", None, "metrics.read"),
    ("GET", "/bff/analytics/events?kind=error&user_id=5", None, "activity.read"),
]


@pytest.mark.parametrize("role", ROLES)
def test_the_role_table_route_by_route(role, harness):
    h = harness(role)
    member = Member("dev@localhost", role)
    for method, path, body, capability in ROUTES:
        audit_before = len(h.stub.store.audit)
        r = h.get(path) if method == "GET" else h.send(method, path, body)
        if member.can(capability):
            # Allowed here and by the admin API: the two tables agree.
            assert r.status_code == 200, (role, method, path, r.text)
        else:
            assert r.status_code == 403, (role, method, path, r.status_code)
            assert r.json()["error"]["code"] == "forbidden"
            assert len(h.stub.store.audit) == audit_before, "a refused call must not reach the admin API"
    for path in ("/bff/me", "/bff/health"):
        assert h.get(path).status_code == 200


def test_every_bff_route_is_in_the_table():
    """A route added without a decision about who may use it fails this test."""
    from bff.app import routes as pkg

    served = set()
    for module in (
        pkg.me,
        pkg.overview,
        pkg.users,
        pkg.usage,
        pkg.tickets,
        pkg.events,
        pkg.plans,
        pkg.orgs,
        pkg.security,
        pkg.activity,
        pkg.audit,
        pkg.config,
    ):
        for route in module.router.routes:
            for method in route.methods:
                served.add((method, "/bff" + route.path))
    concrete = [(m, p.split("?")[0]) for m, p, _, _ in ROUTES] + [
        ("GET", "/bff/me"),
        ("GET", "/bff/health"),
        ("GET", "/bff/events/stream"),
    ]

    def matches(template: str, path: str) -> bool:
        return re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), path) is not None

    for method, template in served:
        assert any(m == method and matches(template, p) for m, p in concrete), (method, template)
    assert len(served) == len(concrete)


# --- validation before forwarding -------------------------------------------------------------
@pytest.mark.parametrize(
    "method,path,body,message",
    [
        ("POST", "/bff/users/5/reveal-email", {"reason": "hi"}, "reason: String should have at least 5 characters"),
        (
            "POST",
            "/bff/users/5/reveal-email",
            {"reason": "A good reason", "email": "x"},
            "email: Extra inputs are not permitted",
        ),
        ("POST", "/bff/users/5/sign-out-everywhere", {}, "reason: Field required"),
        ("PATCH", "/bff/tickets/3", {"status": "answered"}, "status: Input should be"),
        ("PATCH", "/bff/tickets/3", {"tags": ["Has Spaces"]}, "tags.0: String should match pattern"),
        ("POST", "/bff/tickets/3/messages", {"body": "   "}, "body: String should have at least 1 character"),
        (
            "POST",
            "/bff/tickets/3/messages",
            {"body": "x" * 10_001},
            "body: String should have at most 10000 characters",
        ),
        ("PUT", "/bff/users/5/plan", {"plan_id": "Plus!", "note": "why not"}, "plan_id: String should match pattern"),
        (
            "POST",
            "/bff/plans",
            {"id": "pro", "name": "Pro", "limits": {"monthly_ai_tokens": -1}},
            "limits.monthly_ai_tokens",
        ),
        (
            "POST",
            "/bff/plans",
            {"id": "pro", "name": "Pro", "limits": {"unlimited_everything": True}},
            "limits.unlimited_everything: Extra inputs",
        ),
        ("GET", "/bff/users?limit=500", None, "limit: Input should be less than or equal to 100"),
        ("GET", "/bff/users?kind=robot", None, "kind: Input should be"),
        ("GET", "/bff/users/0", None, "user_id: Input should be greater than or equal to 1"),
        ("GET", "/bff/users/abc", None, "user_id: Input should be a valid integer"),
        ("GET", "/bff/overview?from=2026-10-10&to=2026-10-01", None, "The start of the range is after its end."),
        ("GET", "/bff/overview?from=yesterday", None, "from: Input should be a valid date"),
        ("GET", "/bff/users?cursor=not%20a%20cursor", None, "cursor: String should match pattern"),
        ("GET", "/bff/tickets?assignee=anyone", None, "assignee: String should match pattern"),
        ("GET", "/bff/audit?action=DROP%20TABLE", None, "action: String should match pattern"),
    ],
)
def test_bad_input_is_refused_before_anything_is_forwarded(method, path, body, message, harness):
    h = harness("owner")
    audit_before = len(h.stub.store.audit)
    r = h.get(path) if method == "GET" else h.send(method, path, body)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "invalid"
    assert r.json()["error"]["message"].startswith(message), r.json()
    assert len(h.stub.store.audit) == audit_before


def test_validation_errors_never_echo_what_was_sent(harness):
    h = harness("owner")
    r = h.send("POST", "/bff/users/5/reveal-email", {"reason": "hi", "secret": "CANARY-7f3a-DO-NOT-LEAK"})
    assert "CANARY" not in r.text


# --- what is forwarded --------------------------------------------------------------------------
def test_reveal_forwards_the_reason_and_is_audited_once(harness):
    h = harness("support")
    before = len(h.stub.store.audit)
    r = h.send("POST", "/bff/users/5/reveal-email", {"reason": "  Replying by email to AN-0003  ", "ticket_id": 3})
    assert r.status_code == 200
    assert r.json() == {"email": h.stub.store.users[5].email, "first_name": h.stub.store.users[5].first_name}
    rows = h.stub.store.audit[before:]
    assert len(rows) == 1
    row = rows[0]
    assert (row.actor_email, row.actor_role, row.action, row.target_type, row.target_id) == (
        "dev@localhost",
        "support",
        "user.reveal_email",
        "user",
        "5",
    )
    assert row.reason == "Replying by email to AN-0003" and row.details == {"ticket_id": 3}


def test_a_refused_privileged_action_is_audited_by_the_admin_api(harness):
    # The BFF lets support through to sign-out; the admin API refuses an empty reason
    # after trimming, and still writes its one audit row.
    h = harness("support")
    before = len(h.stub.store.audit)
    r = h.send("POST", "/bff/users/99999/sign-out-everywhere", {"reason": "Lost phone, asked us"})
    assert r.status_code == 404
    assert len(h.stub.store.audit) == before + 1
    assert h.stub.store.audit[-1].details == {"status": 404}


def test_ticket_changes_forward_only_what_was_sent(harness):
    h = harness("support")
    ticket = h.stub.store.tickets[3]
    ticket.assignee_email = "maya@anothernote.app"
    r = h.send("PATCH", "/bff/tickets/3", {"priority": "urgent"})
    assert r.status_code == 200 and ticket.priority == "urgent" and ticket.assignee_email == "maya@anothernote.app"
    r = h.send("PATCH", "/bff/tickets/3", {"assignee_email": None, "tags": ["safari", "Safari", "audio"]})
    assert r.status_code == 200 and ticket.assignee_email is None and ticket.tags == ["safari", "audio"]


def test_assignee_me_means_the_actor(harness):
    h = harness("support")
    h.send("PATCH", "/bff/tickets/7", {"assignee_email": "DEV@localhost"})
    items = h.get("/bff/tickets?assignee=me").json()["items"]
    assert [t["id"] for t in items] == [7]


def test_a_staff_reply_moves_the_ticket_to_waiting_on_user(harness):
    h = harness("support")
    ticket = next(t for t in h.stub.store.tickets.values() if t.status == "open")
    r = h.send("POST", f"/bff/tickets/{ticket.id}/messages", {"body": "Hi! Could you tell us which browser you use?"})
    assert r.status_code == 200 and r.json()["author"] == "staff" and r.json()["internal"] is False
    assert ticket.status == "waiting_on_user" and ticket.assignee_email == "dev@localhost"
    note = h.send("POST", f"/bff/tickets/{ticket.id}/messages", {"body": "Checked the logs.", "internal": True})
    assert note.json()["internal"] is True and ticket.status == "waiting_on_user"
    assert h.stub.store.audit[-1].action == "ticket.note"


# --- how admin API failures look in the browser ---------------------------------------------------
def fake(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    "status,payload,expected_status,expected",
    [
        (
            401,
            {"error": {"code": "unauthorized", "message": "bad signature"}},
            502,
            ("unavailable", "The admin API refused this app's credentials. Tell the owner."),
        ),
        (403, {"error": {"code": "forbidden", "message": "Owners only."}}, 403, ("forbidden", "Owners only.")),
        (404, {"error": {"code": "not_found", "message": "No such account."}}, 404, ("not_found", "No such account.")),
        (
            409,
            {"error": {"code": "conflict", "message": "This account is deleted."}},
            409,
            ("conflict", "This account is deleted."),
        ),
        (422, {"detail": [{"loc": ["body", "reason"]}]}, 400, ("invalid", "That request is not valid.")),
        (
            400,
            {"error": {"code": "invalid", "message": "a reason is required"}},
            400,
            ("invalid", "a reason is required"),
        ),
        (429, {}, 429, ("unavailable", "Too many requests. Try again in a moment.")),
        (
            500,
            {"error": {"code": "unavailable", "message": 'psycopg2.errors.UndefinedTable: relation "topics"'}},
            502,
            ("unavailable", "The admin API had a problem. Try again shortly."),
        ),
        (503, None, 502, ("unavailable", "The admin API had a problem. Try again shortly.")),
    ],
)
def test_admin_api_errors_are_mapped(status, payload, expected_status, expected, harness):
    transport = fake(
        lambda request: httpx.Response(status, json=payload)
        if payload is not None
        else httpx.Response(status, text="<html>oops</html>")
    )
    h = harness("owner", transport=transport)
    r = h.get("/bff/users/5")
    assert r.status_code == expected_status
    assert (r.json()["error"]["code"], r.json()["error"]["message"]) == expected
    assert "psycopg2" not in r.text


def test_messages_are_cleaned_and_capped(harness):
    long = "line one\nline two\x00" + "x" * 1000
    h = harness(
        "owner",
        transport=fake(lambda request: httpx.Response(404, json={"error": {"code": "not_found", "message": long}})),
    )
    message = h.get("/bff/users/5").json()["error"]["message"]
    assert "\n" not in message and "\x00" not in message and len(message) == 300


def test_a_connect_error_is_retried_once(harness):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"note": "Study content is never shown in the admin app."})

    h = harness("owner", transport=fake(handler))
    assert h.get("/bff/users/5").json() == {"note": "Study content is never shown in the admin app."}
    assert len(calls) == 2
    # The same signed request went twice: nothing reached the admin API the first time.
    assert calls[0].headers["x-admin-request-id"] == calls[1].headers["x-admin-request-id"]


def test_the_admin_api_down_is_503_after_one_retry(harness):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("refused", request=request)

    h = harness("owner", transport=fake(handler))
    r = h.get("/bff/users/5")
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable" and len(calls) == 2


def test_a_timeout_is_not_retried(harness):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    h = harness("owner", transport=fake(handler))
    r = h.send("POST", "/bff/users/5/sign-out-everywhere", REASON)
    assert r.status_code == 504 and len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>not json</html>", headers={"content-type": "text/html"}),
        httpx.Response(200, content=b"{not json", headers={"content-type": "application/json"}),
        httpx.Response(200, content=b"[" + b"0," * 5_000_000 + b"0]", headers={"content-type": "application/json"}),
    ],
)
def test_answers_that_are_not_json_or_too_big_are_502(response, harness):
    h = harness("owner", transport=fake(lambda request: response))
    r = h.get("/bff/users/5")
    assert r.status_code == 502 and r.json()["error"]["code"] == "unavailable"


def test_the_request_the_admin_api_sees(harness):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": [], "next_cursor": None})

    h = harness("support", transport=fake(handler))
    h.get("/bff/users?q=%20A%2Bb@Example.com%20&kind=standard&active=7d", headers={"Cookie": "CF_Authorization=secret"})
    request = seen[0]
    assert request.url.raw_path == b"/admin/v1/users?q=A%2Bb%40Example.com&kind=standard&active=7d&limit=50"
    assert request.headers["x-admin-actor"] == "dev@localhost" and request.headers["x-admin-role"] == "support"
    # Nothing of the browser's own request travels on: no cookies, no Access token.
    assert "cookie" not in request.headers and "cf-access-jwt-assertion" not in request.headers
    assert request.headers["authorization"].startswith("Bearer ")
