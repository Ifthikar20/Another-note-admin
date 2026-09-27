"""
Cloudflare Access: checking the token Cloudflare puts on every request it lets through.

Cloudflare signs a JWT for the application and sends it in the Cf-Access-Jwt-Assertion
header. It is verified here on every request, not trusted because it arrived: RS256 only,
against the team's published keys (https://<team>/cdn-cgi/access/certs, cached for an
hour), `aud` must contain this application's AUD tag, `iss` must be the team domain, and
it must not have expired. The `email` claim is the actor.

A missing or invalid token is AccessDenied (401, no detail). Keys that cannot be fetched
at all are AccessUnavailable (503): that is our problem, not the person's.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

import httpx
import jwt

logger = logging.getLogger("bff.access")

HEADER = "cf-access-jwt-assertion"
KEYS_TTL = 3600.0  # seconds a fetched key set is trusted before it is fetched again
UNKNOWN_KID_THROTTLE = 60.0  # a token signed with a key we don't know refetches at most this often
RETRY_FLOOR = 5.0  # never fetch more often than this, even while the endpoint fails
LEEWAY = 10  # seconds of clock skew allowed on exp and nbf
MAX_TOKEN_BYTES = 8192


class AccessDenied(Exception):
    """No token, or one that does not verify."""


class AccessUnavailable(Exception):
    """The team's signing keys could not be fetched, and none were fetched before."""


class AccessVerifier:
    def __init__(self, team_domain: str, audience: str, http: Optional[httpx.AsyncClient] = None):
        self.issuer = f"https://{team_domain}"
        self.certs_url = f"https://{team_domain}/cdn-cgi/access/certs"
        self.audience = audience
        self._http = http
        self._keys: dict[str, Any] = {}
        self._fetched_at: Optional[float] = None  # last successful fetch
        self._attempted_at: Optional[float] = None  # last fetch, successful or not
        self._lock = asyncio.Lock()

    async def verify(self, token: Optional[str]) -> str:
        """The verified email of the person, lower-cased."""
        if not token or len(token) > MAX_TOKEN_BYTES:
            raise AccessDenied
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise AccessDenied from None
        if header.get("alg") != "RS256":
            raise AccessDenied
        key = await self._key(header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=LEEWAY,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError:
            raise AccessDenied from None
        email = claims.get("email")
        if not isinstance(email, str) or "@" not in email:
            # A Cloudflare service token carries no email: it is not a person, so not an actor.
            raise AccessDenied
        return email.strip().lower()

    async def _key(self, kid: Any) -> Any:
        if not isinstance(kid, str) or not kid:
            raise AccessDenied
        if self._due(kid):
            await self._refresh(kid)
        key = self._keys.get(kid)
        if key is None:
            if not self._keys:
                raise AccessUnavailable
            raise AccessDenied
        return key

    def _due(self, kid: str) -> bool:
        now = time.monotonic()
        if self._attempted_at is not None and now - self._attempted_at < RETRY_FLOOR:
            return False
        if self._fetched_at is None or now - self._fetched_at > KEYS_TTL:
            return True
        # Cloudflare rotates its keys and publishes the next one early; a token signed
        # with one we have not seen means our copy is behind.
        return kid not in self._keys and (self._attempted_at is None or now - self._attempted_at > UNKNOWN_KID_THROTTLE)

    async def _refresh(self, kid: str) -> None:
        async with self._lock:
            if not self._due(kid):  # another request refreshed while this one waited
                return
            self._attempted_at = time.monotonic()
            try:
                keys = await self._fetch()
            except Exception as e:  # network, status, JSON: keep the keys we had
                logger.warning("could not fetch Cloudflare Access keys from %s: %s", self.certs_url, type(e).__name__)
                return
            if keys:
                self._keys = keys
                self._fetched_at = time.monotonic()

    async def _fetch(self) -> dict[str, Any]:
        client = self._http or httpx.AsyncClient(timeout=5.0)
        try:
            r = await client.get(self.certs_url, timeout=5.0)
            r.raise_for_status()
            data = r.json()
        finally:
            if client is not self._http:
                await client.aclose()
        keys: dict[str, Any] = {}
        for jwk in data.get("keys", []) if isinstance(data, dict) else []:
            if not isinstance(jwk, dict) or jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
                continue
            kid = jwk.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            try:
                keys[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            except (ValueError, TypeError, jwt.PyJWTError):
                continue
        return keys
