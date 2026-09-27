"""
Signing each call to the admin API (5.8.2).

The stand-in admin API checks signatures with its own code, written from the
specification rather than from bff/app/signing.py, so these tests pin the wire format
down from both sides: a fixed test vector, then the verifier's refusals (wrong token,
skewed time, bad signature, replayed request id, tampered body).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest

from bff.app.admin_client import build_path
from bff.app.signing import canonical_message, signature, signed_headers
from devstub.app import create_stub

from .conftest import KEY, TOKEN, fresh_store

# The fixed vector, also given in the README so the admin API can test against it.
VECTOR = dict(
    method="POST",
    path_with_query="/admin/v1/users/481/reveal-email",
    timestamp=1790516426,
    actor="jane@anothernote.app",
    role="support",
    request_id="1f0c2d9e-8b1a-4c3e-9f5d-2a7b6c4d8e10",
    body=b'{"reason":"Replying to their ticket AN-0042","ticket_id":42}',
)
VECTOR_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
VECTOR_SIGNATURE = "3BMWI3AhFmatma_RJTeyPUMcgBL8V7t1loE-08dQ-0c"  # openssl dgst -sha256 -hmac, see README


def test_the_fixed_vector():
    message = canonical_message(**VECTOR)
    assert message == (
        b"POST\n/admin/v1/users/481/reveal-email\n1790516426\njane@anothernote.app\nsupport\n"
        b"1f0c2d9e-8b1a-4c3e-9f5d-2a7b6c4d8e10\n" + hashlib.sha256(VECTOR["body"]).hexdigest().encode()
    )
    # Computed independently of signing.py:
    expected = (
        base64.urlsafe_b64encode(hmac.new(VECTOR_KEY.encode(), message, hashlib.sha256).digest()).rstrip(b"=").decode()
    )
    assert signature(VECTOR_KEY, message) == expected == VECTOR_SIGNATURE


def test_empty_bodies_hash_as_the_empty_string():
    message = canonical_message("get", "/admin/v1/overview", 1, "a@b.c", "viewer", "rid", b"")
    assert message.startswith(b"GET\n")
    assert message.endswith(b"\ne3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_headers_carry_everything_the_admin_api_checks():
    h = signed_headers(
        service_token="tok",
        signing_key="key",
        method="GET",
        path_with_query="/admin/v1/overview",
        actor="a@b.c",
        role="viewer",
    )
    assert h["Authorization"] == "Bearer tok"
    assert h["X-Admin-Actor"] == "a@b.c" and h["X-Admin-Role"] == "viewer"
    assert len(h["X-Admin-Request-Id"]) == 36 and abs(int(h["X-Admin-Timestamp"]) - time.time()) < 5
    assert "=" not in h["X-Admin-Signature"]


@pytest.mark.parametrize(
    "query,expected",
    [
        (None, "/admin/v1/users"),
        ({"q": "a+b@example.com", "limit": 50}, "/admin/v1/users?q=a%2Bb%40example.com&limit=50"),
        ({"q": "two words/?&=", "kind": None, "role": ""}, "/admin/v1/users?q=two%20words%2F%3F%26%3D"),
        ({"flag": True, "other": False}, "/admin/v1/users?flag=true&other=false"),
        ({"q": "Ωmega"}, "/admin/v1/users?q=%CE%A9mega"),
    ],
)
def test_query_strings_are_encoded_so_nothing_is_re_encoded_on_the_way(query, expected):
    target = build_path("/admin/v1/users", query)
    assert target == expected
    assert httpx.URL("http://admin-api:8001" + target).raw_path.decode() == expected


# --- the verifier's side --------------------------------------------------------------------
@pytest.fixture
def stub():
    app = create_stub(TOKEN, KEY, store=fresh_store())
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://admin-api:8001")


def signed(method: str, target: str, body: bytes = b"", **kw) -> dict[str, str]:
    params = dict(
        service_token=TOKEN,
        signing_key=KEY,
        method=method,
        path_with_query=target,
        actor="jane@anothernote.app",
        role="support",
        body=body,
    )
    params.update(kw)
    return signed_headers(**params)


async def test_a_correctly_signed_request_is_accepted(stub):
    app, client = stub
    body = json.dumps({"reason": "Replying to their ticket"}).encode()
    target = "/admin/v1/users/5/reveal-email"
    r = await client.post(
        target, content=body, headers={**signed("POST", target, body), "Content-Type": "application/json"}
    )
    assert r.status_code == 200, r.text
    target = build_path("/admin/v1/users", {"q": "a+b c@example.com", "limit": 5})
    r = await client.get(target, headers=signed("GET", target))
    assert r.status_code == 200, r.text
    assert app.state.stub.refusals == []


@pytest.mark.parametrize(
    "case",
    [
        "wrong_token",
        "skewed_time",
        "bad_signature",
        "tampered_body",
        "tampered_query",
        "tampered_actor",
        "tampered_role",
        "wrong_key",
        "missing_header",
    ],
)
async def test_the_verifier_refuses(case, stub):
    app, client = stub
    body = b'{"reason":"Replying to their ticket"}'
    target = "/admin/v1/users/5/reveal-email"
    sent_target, sent_body = target, body
    if case == "wrong_token":
        headers = signed("POST", target, body, service_token="x" * 40)
    elif case == "skewed_time":
        headers = signed("POST", target, body, timestamp=int(time.time()) - 61)
    elif case == "wrong_key":
        headers = signed("POST", target, body, signing_key="y" * 40)
    else:
        headers = signed("POST", target, body)
    if case == "bad_signature":
        headers["X-Admin-Signature"] = headers["X-Admin-Signature"][:-2] + (
            "AA" if not headers["X-Admin-Signature"].endswith("AA") else "BB"
        )
    if case == "tampered_body":
        sent_body = b'{"reason":"Something else entirely"}'
    if case == "tampered_query":
        sent_target = target + "?x=1"
    if case == "tampered_actor":
        headers["X-Admin-Actor"] = "sam@anothernote.app"
    if case == "tampered_role":
        headers["X-Admin-Role"] = "owner"
    if case == "missing_header":
        del headers["X-Admin-Request-Id"]
    r = await client.post(sent_target, content=sent_body, headers={**headers, "Content-Type": "application/json"})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "unauthorized", "message": "not signed correctly"}}


async def test_a_replayed_request_id_is_refused(stub):
    app, client = stub
    target = "/admin/v1/overview"
    headers = signed("GET", target)
    assert (await client.get(target, headers=headers)).status_code == 200
    assert (await client.get(target, headers=headers)).status_code == 401
    assert app.state.stub.refusals == ["request id already used"]


async def test_padding_is_optional_for_the_verifier(stub):
    _, client = stub
    target = "/admin/v1/overview"
    headers = signed("GET", target)
    headers["X-Admin-Signature"] += "="
    assert (await client.get(target, headers=headers)).status_code == 200
