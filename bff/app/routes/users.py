"""The Users page and a person's page: masked rows, counts, usage, and the audited actions."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Path, Query, Request

from .. import contract as C
from ..admin_client import seg
from ..deps import API, Cursor, FromDate, Limit, ToDate, dates, require
from ..members import Member
from ._forward import forward
from .bodies import PlanAssignBody, ReasonBody, RevealEmailBody

router = APIRouter()
UserId = Annotated[int, Path(ge=1, le=2**31 - 1)]


def _user(user_id: int, rest: str = "") -> str:
    return f"{API}/users/{seg(user_id)}{rest}"


@router.get("/users")
async def list_users(
    request: Request,
    member: Annotated[Member, Depends(require("users.read"))],
    # An id, the start of a child's username, or an exact email (the admin API looks that
    # up by hash, so the address is never revealed by searching).
    q: Annotated[Optional[str], Query(max_length=254)] = None,
    kind: Optional[Literal["standard", "managed_child"]] = None,
    role: Optional[Literal["student", "teacher", "none"]] = None,
    plan: Annotated[Optional[str], Query(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")] = None,
    org: Annotated[Optional[int], Query(ge=1)] = None,
    active: Optional[Literal["today", "7d", "30d", "never"]] = None,
    status: Optional[Literal["active", "deactivated", "deleted"]] = None,
    sort: Optional[Literal["newest", "oldest", "last_seen", "last_sign_in", "cost_30d", "tokens_30d"]] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    query = {
        "q": q.strip() if q else None,
        "kind": kind,
        "role": role,
        "plan": plan,
        "org": org,
        "active": active,
        "status": status,
        "sort": sort,
        "cursor": cursor,
        "limit": limit,
    }
    return await forward(request, "GET", f"{API}/users", member, query=query, shape=C.UserList)


@router.get("/users/{user_id}")
async def get_user(request: Request, user_id: UserId, member: Annotated[Member, Depends(require("users.read"))]):
    return await forward(request, "GET", _user(user_id), member, shape=C.UserDetail)


@router.post("/users/{user_id}/reveal-email")
async def reveal_email(
    request: Request,
    user_id: UserId,
    body: RevealEmailBody,
    member: Annotated[Member, Depends(require("users.reveal_email"))],
):
    return await forward(
        request,
        "POST",
        _user(user_id, "/reveal-email"),
        member,
        body=body.model_dump(mode="json"),
        shape=C.RevealedEmail,
    )


@router.get("/users/{user_id}/sessions")
async def sessions(request: Request, user_id: UserId, member: Annotated[Member, Depends(require("users.read"))]):
    return await forward(request, "GET", _user(user_id, "/sessions"), member, shape=C.SessionList)


@router.post("/users/{user_id}/sign-out-everywhere")
async def sign_out_everywhere(
    request: Request, user_id: UserId, body: ReasonBody, member: Annotated[Member, Depends(require("users.sign_out"))]
):
    return await forward(
        request,
        "POST",
        _user(user_id, "/sign-out-everywhere"),
        member,
        body=body.model_dump(mode="json"),
        shape=C.SignOutResult,
    )


@router.post("/users/{user_id}/deactivate")
async def deactivate(
    request: Request, user_id: UserId, body: ReasonBody, member: Annotated[Member, Depends(require("users.set_active"))]
):
    return await forward(
        request, "POST", _user(user_id, "/deactivate"), member, body=body.model_dump(mode="json"), shape=C.ActiveResult
    )


@router.post("/users/{user_id}/reactivate")
async def reactivate(
    request: Request, user_id: UserId, body: ReasonBody, member: Annotated[Member, Depends(require("users.set_active"))]
):
    return await forward(
        request, "POST", _user(user_id, "/reactivate"), member, body=body.model_dump(mode="json"), shape=C.ActiveResult
    )


@router.get("/users/{user_id}/usage")
async def usage(
    request: Request,
    user_id: UserId,
    member: Annotated[Member, Depends(require("metrics.read"))],
    from_: FromDate = None,
    to: ToDate = None,
    group: Literal["day", "feature", "provider", "model"] = "day",
):
    return await forward(
        request,
        "GET",
        _user(user_id, "/usage"),
        member,
        query={**dates(from_, to), "group": group},
        shape=C.UsageSummary,
    )


@router.get("/users/{user_id}/auth-events")
async def auth_events(
    request: Request,
    user_id: UserId,
    member: Annotated[Member, Depends(require("users.auth_events"))],
    cursor: Cursor = None,
    limit: Limit = 50,
):
    return await forward(
        request,
        "GET",
        _user(user_id, "/auth-events"),
        member,
        query={"cursor": cursor, "limit": limit},
        shape=C.AuthEventList,
    )


@router.get("/users/{user_id}/tickets")
async def tickets(
    request: Request,
    user_id: UserId,
    member: Annotated[Member, Depends(require("users.tickets"))],
    cursor: Cursor = None,
    limit: Limit = 50,
):
    return await forward(
        request, "GET", _user(user_id, "/tickets"), member, query={"cursor": cursor, "limit": limit}, shape=C.TicketList
    )


@router.get("/users/{user_id}/plan")
async def get_plan(request: Request, user_id: UserId, member: Annotated[Member, Depends(require("users.read"))]):
    return await forward(request, "GET", _user(user_id, "/plan"), member, shape=C.SubjectPlan)


@router.put("/users/{user_id}/plan")
async def put_plan(
    request: Request, user_id: UserId, body: PlanAssignBody, member: Annotated[Member, Depends(require("plans.write"))]
):
    return await forward(
        request, "PUT", _user(user_id, "/plan"), member, body=body.model_dump(mode="json"), shape=C.Assignment
    )
