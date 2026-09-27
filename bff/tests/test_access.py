"""Cloudflare Access token verification (6.3.1): good, wrong audience, expired, missing, and more."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization

from bff.app import access
from bff.app.access import AccessDenied, AccessUnavailable, AccessVerifier

from .conftest import AUD, KID, TEAM, JwksServer, jwks_for


def verifier(jwks: JwksServer) -> AccessVerifier:
    return AccessVerifier(TEAM, AUD, http=jwks.client())


async def test_a_good_token_gives_the_email(jwks, make_token):
    assert await verifier(jwks).verify(make_token("Jane@AnotherNote.app")) == "jane@anothernote.app"


async def test_an_audience_list_containing_ours_is_accepted(jwks, make_token):
    assert await verifier(jwks).verify(make_token(aud=["some-other-app", AUD]))


@pytest.mark.parametrize(
    "case",
    ["wrong_audience", "wrong_issuer", "expired", "other_key", "no_email", "email_not_an_address"],
)
async def test_bad_tokens_are_refused(case, jwks, make_token, other_key):
    token = {
        "wrong_audience": lambda: make_token(aud=["another-application"]),
        "wrong_issuer": lambda: make_token(iss="https://someone-else.cloudflareaccess.com"),
        "expired": lambda: make_token(exp_in=-120),
        "other_key": lambda: make_token(key=other_key),
        "no_email": lambda: make_token(email=None, extra={"common_name": "a-service-token"}),
        "email_not_an_address": lambda: make_token(email="not-an-address"),
    }[case]()
    with pytest.raises(AccessDenied):
        await verifier(jwks).verify(token)


@pytest.mark.parametrize("token", [None, "", "not.a.jwt", "x" * 9000])
async def test_missing_or_garbage_tokens_are_refused(token, jwks):
    with pytest.raises(AccessDenied):
        await verifier(jwks).verify(token)


def _unsigned_jwt(header: dict, claims: dict, sign=None) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    head = b64(json.dumps(header).encode())
    body = b64(json.dumps(claims).encode())
    signature = b64(sign(f"{head}.{body}".encode())) if sign else ""
    return f"{head}.{body}.{signature}"


async def test_alg_none_and_hmac_tokens_are_refused(jwks, rsa_key):
    now = int(time.time())
    claims = {"aud": [AUD], "iss": f"https://{TEAM}", "exp": now + 60, "email": "jane@anothernote.app"}
    unsigned = _unsigned_jwt({"alg": "none", "typ": "JWT", "kid": KID}, claims)
    # The old confusion attack: an HS256 token keyed with the (public) RSA key.
    public_pem = rsa_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    confused = _unsigned_jwt(
        {"alg": "HS256", "typ": "JWT", "kid": KID},
        claims,
        sign=lambda m: hmac.new(public_pem, m, hashlib.sha256).digest(),
    )
    v = verifier(jwks)
    for token in (unsigned, confused):
        with pytest.raises(AccessDenied):
            await v.verify(token)


async def test_keys_are_fetched_once_and_cached(jwks, make_token):
    v = verifier(jwks)
    for _ in range(5):
        await v.verify(make_token())
    assert jwks.calls == 1


async def test_a_rotated_key_is_picked_up(jwks, make_token, other_key, monkeypatch):
    v = verifier(jwks)
    await v.verify(make_token())
    # Cloudflare publishes a new key; a token signed with it arrives.
    jwks.document = jwks_for((KID, other_key), ("test-key-2", other_key))
    monkeypatch.setattr(access, "UNKNOWN_KID_THROTTLE", 0.0)
    monkeypatch.setattr(access, "RETRY_FLOOR", 0.0)
    assert await v.verify(make_token(key=other_key, kid="test-key-2")) == "jane@anothernote.app"
    assert jwks.calls == 2


async def test_unknown_key_ids_do_not_hammer_the_endpoint(jwks, make_token, other_key):
    v = verifier(jwks)
    await v.verify(make_token())
    for _ in range(5):
        with pytest.raises(AccessDenied):
            await v.verify(make_token(key=other_key, kid="never-published"))
    assert jwks.calls == 1  # the refetch for an unknown key id is throttled


async def test_keys_that_cannot_be_fetched_are_unavailable_not_denied(jwks, make_token):
    jwks.fail = True
    with pytest.raises(AccessUnavailable):
        await verifier(jwks).verify(make_token())


async def test_keys_already_fetched_survive_an_outage(jwks, make_token, monkeypatch):
    v = verifier(jwks)
    await v.verify(make_token())
    jwks.fail = True
    monkeypatch.setattr(access, "KEYS_TTL", 0.0)  # every call wants a refresh now
    monkeypatch.setattr(access, "RETRY_FLOOR", 0.0)
    assert await v.verify(make_token()) == "jane@anothernote.app"
