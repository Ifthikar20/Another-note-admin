"""
What every request passes through before a route sees it (pure ASGI, so streams pass).

SecurityHeaders   the headers of section 6.6 on every response, and no-store on /bff.
Gatekeeper        who is this, and are they a member? Every request, static files
                  included: a Cloudflare Access token (or, in development, the development
                  identity on a loopback connection), then ADMIN_MEMBERS. /bff answers in
                  JSON; a page load gets a short plain page. Then, for /bff only:
                  X-Requested-With: admin on every call (a cross-site page cannot add it
                  without a preflight, which is never approved), Sec-Fetch-Site must be
                  same-origin when the browser sends it, and a change (POST, PUT, PATCH,
                  DELETE) needs an Origin that is this site. Bodies are capped.
                  Every /bff answer carries X-Request-Id (logs.py); every /bff request
                  is logged, path only, and every refusal is logged as a warning.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional
from urllib.parse import urlsplit

from .access import HEADER as ACCESS_HEADER
from .access import AccessDenied, AccessUnavailable, AccessVerifier
from .logs import RequestTrace, begin_trace, end_trace
from .members import Member
from .settings import Settings, is_loopback

logger = logging.getLogger("bff.request")

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; "
    "object-src 'none'"
)
MAX_BODY_BYTES = 64 * 1024
SAFE_METHODS = ("GET", "HEAD")
# Liveness for the container's health check: answers {"ok": true} and nothing else.
HEALTHZ = "/healthz"

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>AnotherNote Admin</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;line-height:1.5">
<p style="font-size:12px;font-weight:700;letter-spacing:.08em;color:#92400e">ANOTHERNOTE ADMIN</p>
<h1 style="font-size:20px">{title}</h1><p>{body}</p></body></html>"""


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FETCH_SITES = ("cross-site", "same-site", "none")


def _loggable(path: str) -> str:
    """A path as it may appear in a log line: no control characters (no forged lines), bounded."""
    return _CONTROL.sub("?", path)[:300]


def _headers(scope: Scope) -> dict[str, str]:
    # Later duplicates win, which is irrelevant for the headers read here.
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


class SecurityHeaders:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.hsts = settings.is_production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path: str = scope.get("path", "")

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in _OWNED]
                headers += _STATIC_HEADERS
                if self.hsts:
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                existing = {k.lower() for k, _ in headers}
                if path.startswith("/bff/") or path == "/bff" or b"cache-control" not in existing:
                    headers = [(k, v) for k, v in headers if k.lower() != b"cache-control"]
                    if path.startswith("/assets/") and message.get("status") in (200, 304):
                        # Vite names these by their content hash: a new build is a new name.
                        headers.append((b"cache-control", b"public, max-age=31536000, immutable"))
                    else:
                        headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


_STATIC_HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
]
_OWNED = {k for k, _ in _STATIC_HEADERS} | {b"server", b"strict-transport-security"}


async def _json(send: Send, status: int, code: str, message: str, request_id: Optional[str] = None) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if request_id:
        headers.append((b"x-request-id", request_id.encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _page(send: Send, status: int, title: str, body: str) -> None:
    html = _PAGE.format(title=title, body=body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(html)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": html})


class Gatekeeper:
    def __init__(self, app: ASGIApp, settings: Settings, verifier: Optional[AccessVerifier]):
        self.app = app
        self.settings = settings
        self.verifier = verifier
        self.public_origin = None
        if settings.public_origin:
            self.public_origin = urlsplit(settings.public_origin).netloc

    async def identify(self, scope: Scope, headers: dict[str, str]) -> Member:
        """The member making this request. Raises AccessDenied, AccessUnavailable or PermissionError."""
        token = headers.get(ACCESS_HEADER)
        if token and self.verifier is not None:
            email = await self.verifier.verify(token)
        elif self.settings.dev_identity is not None and self._local(scope):
            return self.settings.dev_identity
        else:
            raise AccessDenied
        role = self.settings.members.get(email)
        if role is None:
            raise PermissionError(email)
        return Member(email=email, role=role)

    @staticmethod
    def _local(scope: Scope) -> bool:
        client = scope.get("client") or (None, None)
        server = scope.get("server") or (None, None)
        return is_loopback(client[0]) and is_loopback(server[0])

    def _same_origin(self, headers: dict[str, str]) -> bool:
        origin = headers.get("origin")
        if not origin or origin == "null":
            return False
        netloc = urlsplit(origin).netloc
        if self.public_origin:
            return netloc == self.public_origin
        return bool(netloc) and netloc == headers.get("host")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope.get("path", "") == HEALTHZ:
            return await _json_ok(send)
        trace, token = begin_trace()
        try:
            await self._gate(scope, receive, send, trace)
        finally:
            end_trace(token)

    async def _gate(self, scope: Scope, receive: Receive, send: Send, trace: RequestTrace) -> None:
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        api = path == "/bff" or path.startswith("/bff/")
        headers = _headers(scope)
        started = time.monotonic()
        rid = trace.request_id
        reply_id = rid if api else None
        logged_path = _loggable(path)

        def refused(status: int, reason: str, actor: Optional[str] = None, role: Optional[str] = None) -> None:
            logger.warning(
                "refused %s %s %s actor=%s: %s",
                method,
                logged_path,
                status,
                actor or "-",
                reason,
                extra={
                    "method": method,
                    "path": logged_path,
                    "status": status,
                    "actor": actor,
                    "role": role,
                    "request_id": rid,
                    "reason": reason,
                },
            )

        try:
            member = await self.identify(scope, headers)
        except AccessDenied:
            refused(401, "no valid Cloudflare Access token")
            if api:
                return await _json(send, 401, "unauthorized", "Sign in through Cloudflare Access.", reply_id)
            return await _page(send, 401, "Sign in first", "Open this page through Cloudflare Access to sign in.")
        except AccessUnavailable:
            refused(503, "Cloudflare Access keys unavailable")
            return await _json(
                send, 503, "unavailable", "Sign-in cannot be checked right now. Try again shortly.", reply_id
            )
        except PermissionError as e:
            refused(403, "signed in, but not an admin member", actor=str(e.args[0]) if e.args else None)
            if api:
                return await _json(send, 403, "forbidden", "You are not an admin member.", reply_id)
            return await _page(
                send,
                403,
                "Not an admin member",
                "You are signed in, but not on the admin list. Ask the owner to add you.",
            )

        if api:
            problem: Optional[tuple[int, str, str, str]] = None
            fetch_site = headers.get("sec-fetch-site")
            length = headers.get("content-length")
            if headers.get("x-requested-with") != "admin":
                problem = (403, "Requests must come from the admin app.", "forbidden", "no X-Requested-With: admin")
            elif fetch_site is not None and fetch_site != "same-origin":
                site = fetch_site if fetch_site in _FETCH_SITES else "unexpected value"
                problem = (403, "Requests must come from the admin app.", "forbidden", f"Sec-Fetch-Site {site}")
            elif method not in SAFE_METHODS and not self._same_origin(headers):
                problem = (403, "Changes must come from this site.", "forbidden", "a change without this site's Origin")
            elif length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
                problem = (413, "That request is too large.", "invalid", "body over the size limit")
            if problem is not None:
                status, message, code, reason = problem
                refused(status, reason, member.email, member.role)
                return await _json(send, status, code, message, reply_id)
        elif method not in SAFE_METHODS:
            refused(405, "a change outside /bff", member.email, member.role)
            return await _json(send, 405, "invalid", "Method not allowed.")

        scope.setdefault("state", {})["member"] = member
        status_holder = {"status": 0}

        async def send_logged(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                if api:
                    message = {**message, "headers": [*message.get("headers", []), (b"x-request-id", rid.encode())]}
            await send(message)

        try:
            await self.app(scope, _capped(receive), send_logged)
        except Exception:
            status_holder["status"] = status_holder["status"] or 500
            raise
        finally:
            if api:
                # Path only: queries can hold what staff searched for (an exact email).
                duration = round((time.monotonic() - started) * 1000)
                logger.info(
                    "%s %s %s %dms actor=%s role=%s rid=%s",
                    method,
                    logged_path,
                    status_holder["status"],
                    duration,
                    member.email,
                    member.role,
                    rid,
                    extra={
                        "method": method,
                        "path": logged_path,
                        "status": status_holder["status"],
                        "duration_ms": duration,
                        "actor": member.email,
                        "role": member.role,
                        "request_id": rid,
                        "admin_request_ids": trace.extra_admin_ids(),
                    },
                )


async def _json_ok(send: Send) -> None:
    body = b'{"ok":true}'
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _capped(receive: Receive) -> Receive:
    """A body larger than MAX_BODY_BYTES is cut off (chunked bodies have no length)."""
    received = 0

    async def wrapped() -> dict[str, Any]:
        nonlocal received
        message = await receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > MAX_BODY_BYTES:
                raise BodyTooLarge
        return message

    return wrapped


class BodyTooLarge(Exception):
    pass
