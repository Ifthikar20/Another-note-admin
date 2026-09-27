"""The Security page: failed sign-ins, lockouts, refresh replays, the event stream."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Request

from .. import contract as C
from ..deps import API, Cursor, FromDate, Limit, ToDate, dates, require
from ..members import Member
from ._forward import forward

router = APIRouter()
Reader = Annotated[Member, Depends(require("security.read"))]

AuthEventKind = Literal[
    "sign_in",
    "sign_in_failed",
    "pin_locked",
    "pin_reset",
    "sign_out",
    "sign_out_everywhere",
    "password_changed",
    "refresh_replay",
    "admin_action",
]


@router.get("/security/summary")
async def summary(request: Request, member: Reader, from_: FromDate = None, to: ToDate = None):
    return await forward(
        request, "GET", f"{API}/security/summary", member, query=dates(from_, to), shape=C.SecuritySummary
    )


@router.get("/security/auth-events")
async def auth_events(
    request: Request,
    member: Reader,
    kind: Optional[AuthEventKind] = None,
    from_: FromDate = None,
    to: ToDate = None,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    query = {"kind": kind, **dates(from_, to), "cursor": cursor, "limit": limit}
    return await forward(request, "GET", f"{API}/security/auth-events", member, query=query, shape=C.AuthEventList)
