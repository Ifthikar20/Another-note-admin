"""The Usage and cost page."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request

from .. import contract as C
from ..deps import API, FromDate, ToDate, dates, require
from ..members import Member
from ._forward import forward

router = APIRouter()
Reader = Annotated[Member, Depends(require("metrics.read"))]


@router.get("/usage/summary")
async def summary(
    request: Request,
    member: Reader,
    from_: FromDate = None,
    to: ToDate = None,
    group: Literal["feature", "provider", "model", "day"] = "feature",
):
    return await forward(
        request, "GET", f"{API}/usage/summary", member, query={**dates(from_, to), "group": group}, shape=C.UsageSummary
    )


@router.get("/usage/top-users")
async def top_users(
    request: Request,
    member: Reader,
    from_: FromDate = None,
    to: ToDate = None,
    metric: Literal["cost", "tokens", "characters"] = "cost",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    query = {**dates(from_, to), "metric": metric, "limit": limit}
    return await forward(request, "GET", f"{API}/usage/top-users", member, query=query, shape=C.TopUsers)


@router.get("/usage/anomalies")
async def anomalies(request: Request, member: Reader, date_: Annotated[Optional[date], Query(alias="date")] = None):
    query = {"date": date_.isoformat() if date_ else None}
    return await forward(request, "GET", f"{API}/usage/anomalies", member, query=query, shape=C.Anomalies)
