"""
Shared fixtures: a BFF wired to the stand-in admin API in the same process, and
Cloudflare Access tokens signed with a key made for the test run.
"""

from __future__ import annotations

import gc
import json
import pickle
import time
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Optional

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from bff.app.main import create_app
from bff.app.members import Member
from bff.app.settings import Settings
from devstub.app import create_stub
from devstub.data import Store

warnings.filterwarnings("ignore", message=".*httpx2.*")

TOKEN = "test-service-token-000000000000000000000000"
KEY = "test-signing-key-1111111111111111111111111111"
TEAM = "anothernote.cloudflareaccess.com"
AUD = "aud-tag-0123456789abcdef"
KID = "test-key-1"
FIXED_NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
LOCAL = {"base_url": "http://127.0.0.1:8090", "client": ("127.0.0.1", 50000)}
HEADERS = {"X-Requested-With": "admin"}
SAME_ORIGIN = {"X-Requested-With": "admin", "Origin": "http://127.0.0.1:8090"}

_PRISTINE: dict[str, bytes] = {}


def fresh_store() -> Store:
    """A copy of one seeded store (a pickle round trip is much quicker than seeding)."""
    if "store" not in _PRISTINE:
        _PRISTINE["store"] = pickle.dumps(Store(now=FIXED_NOW))
    # Unpickling makes a lot of objects at once; the cyclic collector would walk them all.
    gc.disable()
    try:
        return pickle.loads(_PRISTINE["store"])
    finally:
        gc.enable()


_SHARED: dict[str, Any] = {}


def shared_stub() -> Any:
    """One stand-in app for the whole run (FastAPI takes a while to build its routes),
    with a freshly seeded store swapped in for every test. The routes hold on to the
    store object, so its contents are replaced rather than the object."""
    from devstub.app import Replay

    if "app" not in _SHARED:
        _SHARED["app"] = create_stub(TOKEN, KEY, store=fresh_store())
    stub = _SHARED["app"].state.stub
    fresh = fresh_store()
    stub.store.__dict__.clear()
    stub.store.__dict__.update(fresh.__dict__)
    stub.replay = Replay()
    stub.refusals = []
    stub.subscribers = set()
    return _SHARED["app"]


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks_for(*keys: tuple[str, rsa.RSAPrivateKey]) -> dict[str, Any]:
    out = []
    for kid, key in keys:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        out.append(jwk)
    return {"keys": out, "public_cert": {}, "public_certs": []}


class JwksServer:
    """The team's /cdn-cgi/access/certs, counting how often it is asked."""

    def __init__(self, document: dict[str, Any]):
        self.document = document
        self.calls = 0
        self.fail = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(f"https://{TEAM}/cdn-cgi/access/certs")
        self.calls += 1
        if self.fail:
            return httpx.Response(503)
        return httpx.Response(200, json=self.document)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def jwks(rsa_key: rsa.RSAPrivateKey) -> JwksServer:
    return JwksServer(jwks_for((KID, rsa_key)))


@pytest.fixture
def make_token(rsa_key: rsa.RSAPrivateKey) -> Callable[..., str]:
    def make(
        email: Optional[str] = "jane@anothernote.app",
        *,
        aud: Any = None,
        iss: Optional[str] = None,
        exp_in: int = 3600,
        key: Optional[rsa.RSAPrivateKey] = None,
        kid: str = KID,
        extra: Optional[dict[str, Any]] = None,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "aud": [AUD] if aud is None else aud,
            "iss": iss or f"https://{TEAM}",
            "iat": now - 5,
            "nbf": now - 5,
            "exp": now + exp_in,
            "type": "app",
            "sub": "0f1e2d3c",
            "country": "GB",
        }
        if email is not None:
            claims["email"] = email
        claims.update(extra or {})
        return jwt.encode(claims, key or rsa_key, algorithm="RS256", headers={"kid": kid})

    return make


def dev_settings(role: str = "owner", **overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        environment="development",
        admin_api_url="http://admin-api:8001",
        service_token=TOKEN,
        signing_key=KEY,
        dev_identity=Member("dev@localhost", role),
    )
    base.update(overrides)
    return Settings(**base)


def prod_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        environment="production",
        admin_api_url="http://admin-api:8001",
        service_token=TOKEN,
        signing_key=KEY,
        cf_team_domain=TEAM,
        cf_aud=AUD,
        members={
            "jane@anothernote.app": "support",
            "sam@anothernote.app": "owner",
            "tom@anothernote.app": "analyst",
            "vi@anothernote.app": "viewer",
        },
    )
    base.update(overrides)
    return Settings(**base)


class Harness:
    """A BFF and the stand-in behind it."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        access_http: Optional[httpx.AsyncClient] = None,
        **client_kw: Any,
    ):
        if transport is None:
            self.stub_app = shared_stub()
            self.stub = self.stub_app.state.stub
            transport = httpx.ASGITransport(app=self.stub_app)
        self.app = create_app(settings, admin_transport=transport, access_http=access_http)
        kw = {**LOCAL, **client_kw}
        self.client = TestClient(self.app, **kw)

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.client.get(path, headers={**HEADERS, **kw.pop("headers", {})}, **kw)

    def send(self, method: str, path: str, body: Any = None, **kw: Any) -> httpx.Response:
        return self.client.request(method, path, json=body, headers={**SAME_ORIGIN, **kw.pop("headers", {})}, **kw)


@pytest.fixture
def harness() -> Callable[..., Harness]:
    made: list[Harness] = []

    def make(role: str = "owner", settings: Optional[Settings] = None, **kw: Any) -> Harness:
        h = Harness(settings or dev_settings(role), **kw)
        made.append(h)
        return h

    yield make
    for h in made:
        h.client.close()
