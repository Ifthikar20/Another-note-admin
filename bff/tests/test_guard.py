"""What every request passes through: identity, membership, CSRF checks, headers, static files."""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import HEADERS, SAME_ORIGIN, dev_settings, prod_settings

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; "
    "object-src 'none'"
)


@pytest.fixture
def spa(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>AnotherNote Admin</title><div id=root></div>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('admin')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    return tmp_path


def production(harness, jwks, **kw):
    return harness(
        settings=prod_settings(**kw),
        access_http=jwks.client(),
        base_url="https://admin.anothernote.app",
        client=("172.18.0.5", 40000),
    )


# --- identity ---------------------------------------------------------------------------------
def test_production_needs_an_access_token_for_everything(harness, jwks, spa):
    h = production(harness, jwks, static_dir=str(spa))
    r = h.get("/bff/me")
    assert r.status_code == 401 and r.json() == {
        "error": {"code": "unauthorized", "message": "Sign in through Cloudflare Access."}
    }
    page = h.client.get("/users/5")
    assert page.status_code == 401 and "text/html" in page.headers["content-type"]
    assert "AnotherNote Admin" not in page.text.split("<body")[0] or "Sign in first" in page.text
    assert h.client.get("/assets/index-abc123.js").status_code == 401


def test_a_member_with_a_good_token_gets_in(harness, jwks, make_token):
    h = production(harness, jwks)
    r = h.get("/bff/me", headers={"Cf-Access-Jwt-Assertion": make_token("Jane@AnotherNote.app")})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "jane@anothernote.app" and body["role"] == "support" and body["dev_identity"] is False
    assert "users.reveal_email" in body["capabilities"] and "audit.read" not in body["capabilities"]
    assert body["sign_out_url"] == "/cdn-cgi/access/logout"
    assert (body["idle_lock_minutes"], body["idle_sign_out_minutes"]) == (15, 60)


def test_a_non_member_gets_403_even_with_a_good_token(harness, jwks, make_token):
    h = production(harness, jwks)
    token = make_token("stranger@anothernote.app")
    r = h.get("/bff/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    page = h.client.get("/", headers={"Cf-Access-Jwt-Assertion": token})
    assert page.status_code == 403 and "Not an admin member" in page.text


@pytest.mark.parametrize("case", ["expired", "wrong_audience", "other_key"])
def test_bad_tokens_get_401(case, harness, jwks, make_token, other_key):
    token = {
        "expired": lambda: make_token(exp_in=-100),
        "wrong_audience": lambda: make_token(aud=["x"]),
        "other_key": lambda: make_token(key=other_key),
    }[case]()
    h = production(harness, jwks)
    assert h.get("/bff/me", headers={"Cf-Access-Jwt-Assertion": token}).status_code == 401


def test_access_keys_unreachable_is_503(harness, jwks, make_token):
    jwks.fail = True
    h = production(harness, jwks)
    assert h.get("/bff/me", headers={"Cf-Access-Jwt-Assertion": make_token()}).status_code == 503


def test_dev_identity_only_for_connections_from_this_machine(harness):
    local = harness("owner")
    assert local.get("/bff/me").json()["dev_identity"] is True
    remote = harness("owner", client=("192.168.1.30", 50000))
    assert remote.get("/bff/me").status_code == 401
    # Loopback client, but a server address that is not: some forwarding in between.
    forwarded = harness("owner", base_url="http://10.0.0.8:8090")
    assert forwarded.get("/bff/me").status_code == 401


def test_healthz_answers_without_identity_and_says_nothing_else(harness, jwks):
    h = production(harness, jwks)
    r = h.client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}


# --- CSRF and fetch checks ----------------------------------------------------------------------
def test_bff_calls_need_x_requested_with(harness):
    h = harness("owner")
    assert h.client.get("/bff/me").status_code == 403
    assert h.client.get("/bff/me", headers={"X-Requested-With": "XMLHttpRequest"}).status_code == 403
    assert h.client.get("/bff/me", headers=HEADERS).status_code == 200


@pytest.mark.parametrize(
    "site,ok", [("same-origin", True), ("same-site", False), ("cross-site", False), ("none", False)]
)
def test_sec_fetch_site_must_be_same_origin_when_sent(harness, site, ok):
    h = harness("owner")
    r = h.get("/bff/me", headers={"Sec-Fetch-Site": site})
    assert (r.status_code == 200) is ok


@pytest.mark.parametrize(
    "origin,ok",
    [
        (None, False),
        ("null", False),
        ("https://evil.example", False),
        ("http://127.0.0.1:9999", False),
        ("http://127.0.0.1:8090", True),
    ],
)
def test_changes_need_a_same_origin_origin(harness, origin, ok):
    h = harness("owner")
    headers = {"X-Requested-With": "admin"}
    if origin:
        headers["Origin"] = origin
    r = h.client.post("/bff/users/5/sign-out-everywhere", json={"reason": "Lost their phone"}, headers=headers)
    assert (r.status_code == 200) is ok, r.text
    if not ok:
        assert r.json()["error"]["message"] == "Changes must come from this site."
        assert h.stub.store.users[5].token_epoch == 0  # nothing reached the admin API


def test_public_origin_overrides_the_host_comparison(harness, jwks, make_token):
    h = production(harness, jwks, public_origin="https://admin.anothernote.app")
    token = make_token("jane@anothernote.app")
    base = {"X-Requested-With": "admin", "Cf-Access-Jwt-Assertion": token}
    ok = h.client.post(
        "/bff/tickets/3/messages",
        json={"body": "Hello"},
        headers={**base, "Origin": "https://admin.anothernote.app", "Host": "admin-web:8080"},
    )
    assert ok.status_code == 200, ok.text
    bad = h.client.post(
        "/bff/tickets/3/messages",
        json={"body": "Hello"},
        headers={**base, "Origin": "https://admin-web:8080", "Host": "admin-web:8080"},
    )
    assert bad.status_code == 403


def test_oversized_bodies_are_refused(harness):
    h = harness("owner")
    r = h.send("POST", "/bff/tickets/3/messages", {"body": "x" * 70_000})
    assert r.status_code == 413


def test_pages_only_take_get(harness, spa):
    h = harness("owner", settings=dev_settings(static_dir=str(spa)))
    assert h.client.post("/users/5", headers=SAME_ORIGIN).status_code == 405


# --- headers -----------------------------------------------------------------------------------
def test_security_headers_on_api_responses(harness):
    r = harness("owner").get("/bff/me")
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    assert r.headers["cache-control"] == "no-store"
    assert "server" not in r.headers
    assert "strict-transport-security" not in r.headers  # development


def test_security_headers_on_refusals_and_hsts_in_production(harness, jwks):
    r = production(harness, jwks).get("/bff/me")
    assert r.status_code == 401
    assert r.headers["content-security-policy"] == CSP and r.headers["cache-control"] == "no-store"
    assert r.headers["strict-transport-security"] == "max-age=31536000"


def test_errors_from_the_admin_api_are_no_store_too(harness):
    r = harness("owner").get("/bff/users/99999")
    assert r.status_code == 404 and r.headers["cache-control"] == "no-store"


# --- the SPA ---------------------------------------------------------------------------------
def test_deep_links_get_the_app_and_assets_are_immutable(harness, spa):
    h = harness("owner", settings=dev_settings(static_dir=str(spa)))
    page = h.client.get("/users/5")
    assert page.status_code == 200 and "AnotherNote Admin" in page.text
    assert page.headers["cache-control"] == "no-store" and page.headers["content-security-policy"] == CSP
    asset = h.client.get("/assets/index-abc123.js")
    assert asset.status_code == 200 and asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert h.client.get("/favicon.svg").status_code == 200


def test_missing_files_are_404_not_the_app(harness, spa):
    h = harness("owner", settings=dev_settings(static_dir=str(spa)))
    assert h.client.get("/assets/index-old999.js").status_code == 404
    assert h.client.get("/robots.txt").status_code == 404


def test_no_path_escapes_the_static_folder(harness, spa):
    (spa.parent / "secret.txt").write_text("not for you")
    h = harness("owner", settings=dev_settings(static_dir=str(spa)))
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"):
        r = h.client.get(path)
        assert "not for you" not in r.text, path


def test_unknown_bff_routes_are_404_never_the_app_or_a_proxy(harness, spa):
    h = harness("owner", settings=dev_settings(static_dir=str(spa)))
    # (Plain ".." segments are removed by browsers and HTTP clients before sending.)
    for path in (
        "/bff/admin/v1/users",
        "/bff/users/5/%2e%2e/%2e%2e/audit",
        "/bff/does-not-exist",
        "/bff/users/5/secret",
    ):
        r = h.get(path)
        assert r.status_code == 404, path
        assert r.headers["content-type"].startswith("application/json")
    assert h.send("DELETE", "/bff/users/5").status_code == 404


def test_searches_never_reach_the_logs(harness, caplog):
    import logging

    h = harness("owner")
    with caplog.at_level(logging.DEBUG):
        h.get("/bff/users?q=jane.doe%40example.com")
    logged = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.INFO)
    assert "jane.doe" not in logged
    assert "GET /bff/users 200" in logged  # the BFF's own line: the path, never the query
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


# --- request ids and logs -------------------------------------------------------------------
def _lines(caplog, name="bff.request"):
    return [r for r in caplog.records if r.name == name]


def test_the_request_id_is_on_the_answer_the_log_line_and_the_audit_row(harness, caplog):
    import logging

    h = harness("owner")
    with caplog.at_level(logging.INFO):
        r = h.get("/bff/users/5")
    assert r.status_code == 200
    rid = r.headers["x-request-id"]
    row = h.stub.store.audit[-1]
    assert (row.action, row.request_id) == ("view.user", rid)
    [line] = [x for x in _lines(caplog) if getattr(x, "request_id", None) == rid]
    assert (line.method, line.path, line.status, line.actor, line.role) == (
        "GET",
        "/bff/users/5",
        200,
        "dev@localhost",
        "owner",
    )
    assert line.admin_request_ids is None


def test_every_admin_call_of_one_request_gets_its_own_id(harness, caplog, monkeypatch):
    import logging

    from bff.app.routes import audit

    monkeypatch.setattr(audit, "EXPORT_PAGE", 10)
    monkeypatch.setattr(audit, "EXPORT_MAX_PAGES", 3)
    h = harness("owner")
    before = len(h.stub.store.audit)
    with caplog.at_level(logging.INFO):
        r = h.get("/bff/audit/export.csv")
    rid = r.headers["x-request-id"]
    ids = [a.request_id for a in h.stub.store.audit[before:]]
    assert len(ids) == 3 and ids[0] == rid and len(set(ids)) == 3
    [line] = [x for x in _lines(caplog) if getattr(x, "request_id", None) == rid]
    assert line.admin_request_ids == ids[1:]


def test_refusals_carry_a_request_id_and_are_logged(harness, jwks, make_token, caplog):
    import logging

    h = production(harness, jwks)
    with caplog.at_level(logging.INFO):
        stranger = h.get("/bff/me", headers={"Cf-Access-Jwt-Assertion": make_token("stranger@anothernote.app")})
        nobody = h.get("/bff/users?q=jane.doe%40example.com")
        bare = h.client.get("/bff/me", headers={"Cf-Access-Jwt-Assertion": make_token("jane@anothernote.app")})
    warnings = [x for x in _lines(caplog) if x.levelno == logging.WARNING]
    by_id = {x.request_id: x for x in warnings}
    assert by_id[stranger.headers["x-request-id"]].status == 403
    assert by_id[stranger.headers["x-request-id"]].actor == "stranger@anothernote.app"
    assert by_id[nobody.headers["x-request-id"]].status == 401
    assert by_id[nobody.headers["x-request-id"]].path == "/bff/users"
    refused = by_id[bare.headers["x-request-id"]]
    assert (refused.status, refused.actor, refused.reason) == (
        403,
        "jane@anothernote.app",
        "no X-Requested-With: admin",
    )
    assert "jane.doe" not in "\n".join(x.getMessage() for x in caplog.records)


def test_log_lines_cannot_be_forged_through_the_path(harness, caplog):
    import logging

    h = harness("owner")
    with caplog.at_level(logging.INFO):
        h.get("/bff/nothing%0A2026-01-01 INFO bff.request GET /bff/audit 200")
    assert all("\n" not in x.getMessage() for x in _lines(caplog))


def test_json_log_lines_hold_only_the_known_fields():
    import json
    import logging

    from bff.app.logs import JsonFormatter

    record = logging.LogRecord("bff.request", logging.INFO, __file__, 1, "GET %s 200", ("/bff/me",), None)
    record.method, record.path, record.status, record.request_id = "GET", "/bff/me", 200, "r-1"
    record.secret = "never written"
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "GET /bff/me 200"
    assert (entry["level"], entry["logger"], entry["status"], entry["request_id"]) == (
        "INFO",
        "bff.request",
        200,
        "r-1",
    )
    assert "secret" not in entry and entry["time"].endswith("+00:00")


def test_configuring_logs_twice_adds_one_handler(monkeypatch):
    import logging

    from bff.app import logs

    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [h for h in root.handlers if not isinstance(h, logs._Handler)])
    level = root.level
    try:
        logs.configure({"LOG_FORMAT": "json"})
        logs.configure({"LOG_FORMAT": "text"})
        mine = [h for h in root.handlers if isinstance(h, logs._Handler)]
        assert len(mine) == 1 and isinstance(mine[0].formatter, logs.JsonFormatter)
    finally:
        root.handlers = [h for h in root.handlers if not isinstance(h, logs._Handler)]
        root.setLevel(level)
