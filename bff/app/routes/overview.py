"""The Overview page: KPIs and the active-user and sign-in series."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from .. import contract as C
from ..deps import API, FromDate, ToDate, dates, require
from ..members import Member
from ._forward import forward

router = APIRouter()
Reader = Annotated[Member, Depends(require("metrics.read"))]


@router.get("/overview")
async def overview(request: Request, member: Reader, from_: FromDate = None, to: ToDate = None):
    return await forward(request, "GET", f"{API}/overview", member, query=dates(from_, to), shape=C.Overview)


@router.get("/metrics/active-users")
async def active_users(
    request: Request,
    member: Reader,
    from_: FromDate = None,
    to: ToDate = None,
    granularity: Annotated[Literal["day"], Query()] = "day",
):
    return await forward(
        request,
        "GET",
        f"{API}/metrics/active-users",
        member,
        query={**dates(from_, to), "granularity": granularity},
        shape=C.ActiveUsers,
    )


@router.get("/metrics/sign-ins")
async def sign_ins(
    request: Request,
    member: Reader,
    from_: FromDate = None,
    to: ToDate = None,
    group: Annotated[Literal["method"], Query()] = "method",
):
    return await forward(
        request, "GET", f"{API}/metrics/sign-ins", member, query={**dates(from_, to), "group": group}, shape=C.SignIns
    )


@router.get("/metrics/online-now")
async def online_now(request: Request, member: Reader):
    return await forward(request, "GET", f"{API}/metrics/online-now", member, shape=C.OnlineNow)
