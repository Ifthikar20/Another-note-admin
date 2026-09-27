"""Who is signed in, and whether the admin API is up."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .. import contract as C
from ..admin_client import AdminApiError
from ..deps import API, current_member
from ..members import Member
from ..shape import prune

router = APIRouter()


@router.get("/me")
async def me(request: Request, member: Annotated[Member, Depends(current_member)]) -> JSONResponse:
    settings = request.app.state.settings
    return JSONResponse(
        {
            "email": member.email,
            "role": member.role,
            "capabilities": member.capabilities,
            "environment": settings.environment,
            "dev_identity": settings.dev_identity is not None and member == settings.dev_identity,
            "version": settings.version,
            # Cloudflare Access ends the session at this path of the application's own
            # hostname; without Access (development) there is nothing to sign out of.
            "sign_out_url": "/cdn-cgi/access/logout" if settings.access_enabled else None,
            "idle_lock_minutes": settings.idle_lock_minutes,
            "idle_sign_out_minutes": settings.idle_sign_out_minutes,
        }
    )


@router.get("/health")
async def health(request: Request, member: Annotated[Member, Depends(current_member)]) -> JSONResponse:
    try:
        upstream = prune(await request.app.state.admin.call("GET", f"{API}/health", actor=member), C.Health)
    except AdminApiError as e:
        return JSONResponse(
            {
                "ok": False,
                "bff_version": request.app.state.settings.version,
                "admin_api": {"ok": False, "error": e.message},
            }
        )
    return JSONResponse(
        {"ok": bool(upstream.get("ok")), "bff_version": request.app.state.settings.version, "admin_api": upstream}
    )
