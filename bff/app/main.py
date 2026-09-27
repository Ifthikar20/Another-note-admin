"""
The admin app's server: the built SPA, the /bff routes, and the guard in front of both.

    uvicorn bff.app.main:app --port 8090        (development, 127.0.0.1 by default)
    python -m bff.app                           (the container: ADMIN_BIND_HOST, ADMIN_PORT)

`app` is built on first access, so importing this module (the tests do) does not read
the environment; uvicorn's access to `app` does, and a bad configuration stops start-up.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import logs
from .access import AccessVerifier
from .admin_client import AdminApiError, AdminClient
from .guard import BodyTooLarge, Gatekeeper, SecurityHeaders
from .routes import router as bff_router
from .settings import Settings, load_settings

logger = logging.getLogger("bff")

_CODES = {
    400: "invalid",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "invalid",
    409: "conflict",
    413: "invalid",
    422: "invalid",
}
_MESSAGES = {
    400: "That request is not valid.",
    401: "Sign in through Cloudflare Access.",
    403: "Your role cannot do this.",
    404: "Not found.",
    405: "Method not allowed.",
    409: "That conflicts with a change made meanwhile.",
    413: "That request is too large.",
}


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def quiet_http_logs() -> None:
    """httpx logs every request's full URL at INFO, query string included, and a query
    can be what staff searched for (an exact email). The BFF logs its own calls, path
    only; httpx and httpcore may speak up for warnings and errors."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def create_app(
    settings: Optional[Settings] = None,
    *,
    admin_transport: Optional[httpx.AsyncBaseTransport] = None,
    access_http: Optional[httpx.AsyncClient] = None,
) -> FastAPI:
    settings = settings or load_settings()
    quiet_http_logs()
    admin_client = AdminClient(settings, transport=admin_transport)
    verifier = (
        AccessVerifier(settings.cf_team_domain, settings.cf_aud, http=access_http)  # type: ignore[arg-type]
        if settings.access_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.dev_identity:
            logger.warning(
                "DEVELOPMENT IDENTITY in use: every local request is %s (%s)",
                settings.dev_identity.email,
                settings.dev_identity.role,
            )
        if not settings.static_dir:
            logger.info("no built SPA found: serving /bff only (run `npm run build` in web/, or use `npm run dev`)")
        try:
            yield
        finally:
            await admin_client.aclose()

    app = FastAPI(
        title="AnotherNote Admin",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.admin = admin_client

    @app.exception_handler(AdminApiError)
    async def _admin_error(_: Request, exc: AdminApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) and exc.status_code < 500 else None
        return _error(
            exc.status_code,
            _CODES.get(exc.status_code, "unavailable"),
            detail or _MESSAGES.get(exc.status_code, "Something went wrong."),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Where and what, never the value that was sent.
        first: dict[str, Any] = exc.errors()[0] if exc.errors() else {}
        loc = list(first.get("loc", ()))
        if loc and loc[0] in ("body", "query", "path", "header", "cookie"):
            loc = loc[1:]  # where it came from, not a field name ("body" is also a field)
        where = ".".join(str(p) for p in loc)
        message = f"{where}: {first.get('msg', 'not valid')}" if where else str(first.get("msg", "not valid"))
        return _error(400, "invalid", message[:300])

    @app.exception_handler(BodyTooLarge)
    async def _too_large(_: Request, __: BodyTooLarge) -> JSONResponse:
        return _error(413, "invalid", "That request is too large.")

    app.include_router(bff_router, prefix="/bff")

    @app.api_route("/bff/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def _unknown_bff(rest: str) -> JSONResponse:
        # Only the routes above exist: there is no generic proxy behind /bff.
        return _error(404, "not_found", "No such route.")

    _mount_spa(app, settings.static_dir)

    # Outermost last: SecurityHeaders wraps the Gatekeeper, so its refusals carry them too.
    app.add_middleware(Gatekeeper, settings=settings, verifier=verifier)
    app.add_middleware(SecurityHeaders, settings=settings)
    return app


def _mount_spa(app: FastAPI, static_dir: Optional[str]) -> None:
    if not static_dir:

        @app.get("/{path:path}", include_in_schema=False)
        async def _no_spa(path: str) -> Response:
            return Response(
                "The admin UI is not built. Run `npm run build` in web/, or `npm run dev` and open port 8080.\n",
                media_type="text/plain",
                status_code=404,
            )

        return

    root = Path(static_dir).resolve()
    index = root / "index.html"
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def _spa(path: str) -> Response:
        if path:
            candidate = (root / path).resolve()
            if candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            if "." in path.rsplit("/", 1)[-1]:
                # A missing file (an old hashed asset, a typo), not a page of the app.
                return Response("Not found.\n", media_type="text/plain", status_code=404)
        return FileResponse(index, media_type="text/html")


def __getattr__(name: str) -> Any:
    # `bff.app.main:app` for uvicorn, built on first access (PEP 562).
    if name == "app":
        logs.configure(os.environ)
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
