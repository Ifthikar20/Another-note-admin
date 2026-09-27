"""
The Activity page: what people did in the app, and what went wrong (admin_analytics_v).

Page views, a few key actions, and errors, as the student app records them. Only the
view's columns come back (kind, name, path, the three utm_* tags): an error shows its
message, never its stack, and no user agent, browser id or other tag is ever shown.
Totals and the grouped errors are for every role; the event-by-event log, with who did
what, is for owner and support.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request

from .. import contract as C
from ..deps import API, Cursor, FromDate, Limit, ToDate, dates, require
from ..members import Member
from ._forward import forward

router = APIRouter()


@router.get("/analytics/summary")
async def summary(
    request: Request,
    member: Annotated[Member, Depends(require("metrics.read"))],
    from_: FromDate = None,
    to: ToDate = None,
):
    return await forward(
        request, "GET", f"{API}/analytics/summary", member, query=dates(from_, to), shape=C.AnalyticsSummary
    )


@router.get("/analytics/errors")
async def errors(
    request: Request,
    member: Annotated[Member, Depends(require("metrics.read"))],
    from_: FromDate = None,
    to: ToDate = None,
    q: Annotated[Optional[str], Query(max_length=160)] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    query = {**dates(from_, to), "q": q.strip() if q else None, "cursor": cursor, "limit": limit}
    return await forward(request, "GET", f"{API}/analytics/errors", member, query=query, shape=C.ErrorGroups)


@router.get("/analytics/events")
async def events(
    request: Request,
    member: Annotated[Member, Depends(require("activity.read"))],
    kind: Optional[Literal["view", "action", "error"]] = None,
    name: Annotated[Optional[str], Query(max_length=160)] = None,
    path: Annotated[Optional[str], Query(max_length=300)] = None,
    user_id: Annotated[Optional[int], Query(ge=1, le=2**31 - 1)] = None,
    from_: FromDate = None,
    to: ToDate = None,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    query = {
        "kind": kind,
        "name": name,
        "path": path,
        "user_id": user_id,
        **dates(from_, to),
        "cursor": cursor,
        "limit": limit,
    }
    return await forward(request, "GET", f"{API}/analytics/events", member, query=query, shape=C.AnalyticsEventList)
