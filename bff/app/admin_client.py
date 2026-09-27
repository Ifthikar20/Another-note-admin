"""
The BFF's only way to the admin API: one httpx client, and every call signed.

Calls are made to explicit paths by the route modules (there is no generic proxy). A call
that cannot connect is retried once; nothing else is. Answers are read with a size cap and
must be JSON; errors come back in the admin API's envelope and are mapped to what the
browser should see. A 401 from the admin API means the BFF's own credentials or clock are
wrong, so it becomes a 502 for the browser (the person is signed in; this app is broken).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .members import Member
from .settings import Settings
from .signing import signed_headers

logger = logging.getLogger("bff.admin_client")

TIMEOUT = httpx.Timeout(10.0)
# The admin API sends an SSE comment at least every 30 seconds; silence for longer than
# this means the stream is dead, and the browser reconnects.
STREAM_TIMEOUT = httpx.Timeout(10.0, read=90.0)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_MESSAGE = 300
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class AdminApiError(Exception):
    """An answer for the browser: HTTP status, one of the error codes, and a message."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _encode(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return quote(str(value), safe="")


def build_path(path: str, query: Optional[Mapping[str, Any]] = None) -> str:
    """The request target exactly as it goes on the wire, which is what gets signed.

    Every key and value is percent-encoded with no safe characters, so httpx has nothing
    left to re-encode. Empty and None values are left out; order is kept.
    """
    pairs = [(k, v) for k, v in (query or {}).items() if v is not None and v != ""]
    if not pairs:
        return path
    return path + "?" + "&".join(f"{quote(k, safe='')}={_encode(v)}" for k, v in pairs)


def seg(value: Any) -> str:
    """One path segment (an id), encoded."""
    return quote(str(value), safe="")


def _clean_message(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = _CONTROL.sub(" ", value).strip()
    return value[:MAX_ERROR_MESSAGE] or None


class AdminClient:
    def __init__(self, settings: Settings, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.admin_api_url,
            timeout=TIMEOUT,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": f"anothernote-admin-bff/{settings.version}", "Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _request(
        self,
        method: str,
        path: str,
        *,
        actor: Member,
        query: Optional[Mapping[str, Any]] = None,
        body: Any = None,
        accept: str = "application/json",
        timeout: httpx.Timeout = TIMEOUT,
    ) -> httpx.Request:
        target = build_path(path, query)
        content = b"" if body is None else json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = signed_headers(
            service_token=self._settings.service_token,
            signing_key=self._settings.signing_key,
            method=method,
            path_with_query=target,
            actor=actor.email,
            role=actor.role,
            body=content,
        )
        headers["Accept"] = accept
        if content:
            headers["Content-Type"] = "application/json"
        request = self._client.build_request(method, target, content=content or None, headers=headers, timeout=timeout)
        # What was signed must be what is sent. build_path leaves httpx nothing to change;
        # this makes sure it stays that way.
        if request.url.raw_path.decode("ascii") != target:
            raise RuntimeError(f"request target changed on the way out: {target!r}")
        return request

    async def _send(self, request: httpx.Request) -> httpx.Response:
        for attempt in (1, 2):
            try:
                return await self._client.send(request, stream=True)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Nothing reached the admin API, so the same signed request can go again.
                if attempt == 2:
                    logger.error("admin API unreachable at %s", self._settings.admin_api_url)
                    raise AdminApiError(503, "unavailable", "The admin API is not reachable right now.") from None
                logger.warning("admin API connection failed; retrying once")
            except httpx.TimeoutException:
                raise AdminApiError(504, "unavailable", "The admin API took too long to answer.") from None
            except httpx.HTTPError as e:
                logger.error("admin API request failed: %s", type(e).__name__)
                raise AdminApiError(502, "unavailable", "The admin API could not be reached.") from None
        raise AssertionError("unreachable")

    @staticmethod
    async def _read(response: httpx.Response) -> bytes:
        chunks, size = [], 0
        try:
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise AdminApiError(502, "unavailable", "The admin API sent more than this app accepts.")
                chunks.append(chunk)
        except httpx.TimeoutException:
            raise AdminApiError(504, "unavailable", "The admin API took too long to answer.") from None
        except httpx.HTTPError:
            raise AdminApiError(502, "unavailable", "The admin API connection broke off.") from None
        return b"".join(chunks)

    async def call(
        self,
        method: str,
        path: str,
        *,
        actor: Member,
        query: Optional[Mapping[str, Any]] = None,
        body: Any = None,
    ) -> Any:
        """One JSON call. Returns the decoded body, or raises AdminApiError."""
        response = await self._send(self._request(method, path, actor=actor, query=query, body=body))
        try:
            raw = await self._read(response)
        finally:
            await response.aclose()
        if 200 <= response.status_code < 300:
            if response.status_code == 204 or not raw:
                return None
            if "json" not in response.headers.get("content-type", ""):
                raise AdminApiError(502, "unavailable", "The admin API did not answer in JSON.")
            try:
                return json.loads(raw)
            except ValueError:
                raise AdminApiError(502, "unavailable", "The admin API sent JSON that does not parse.") from None
        raise self._error(response.status_code, raw)

    async def open_stream(
        self, path: str, *, actor: Member, query: Optional[Mapping[str, Any]] = None
    ) -> httpx.Response:
        """A server-sent event stream, open and checked. The caller must aclose() it."""
        request = self._request(
            "GET", path, actor=actor, query=query, accept="text/event-stream", timeout=STREAM_TIMEOUT
        )
        response = await self._send(request)
        if response.status_code != 200:
            try:
                raw = await self._read(response)
            finally:
                await response.aclose()
            raise self._error(response.status_code, raw)
        if not response.headers.get("content-type", "").startswith("text/event-stream"):
            await response.aclose()
            raise AdminApiError(502, "unavailable", "The admin API did not answer with an event stream.")
        return response

    @staticmethod
    def _error(status: int, raw: bytes) -> AdminApiError:
        message = None
        try:
            payload = json.loads(raw) if raw else None
            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                message = _clean_message(payload["error"].get("message"))
        except ValueError:
            pass
        if status == 401:
            logger.error(
                "the admin API refused the BFF's credentials (401): check ADMIN_SERVICE_TOKEN, "
                "ADMIN_SIGNING_KEY and both clocks"
            )
            return AdminApiError(502, "unavailable", "The admin API refused this app's credentials. Tell the owner.")
        if status == 403:
            return AdminApiError(403, "forbidden", message or "Your role cannot do this.")
        if status == 404:
            return AdminApiError(404, "not_found", message or "Not found.")
        if status == 409:
            return AdminApiError(409, "conflict", message or "That conflicts with a change made meanwhile.")
        if status in (400, 422):
            return AdminApiError(400, "invalid", message or "That request is not valid.")
        if status == 429:
            return AdminApiError(429, "unavailable", "Too many requests. Try again in a moment.")
        logger.error("admin API answered %s", status)
        # Never pass an upstream 5xx message on: it could carry a database error.
        return AdminApiError(502, "unavailable", "The admin API had a problem. Try again shortly.")
