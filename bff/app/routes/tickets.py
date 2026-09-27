"""The ticket inbox and a ticket's conversation."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Path, Query, Request

from .. import contract as C
from ..admin_client import seg
from ..deps import API, Cursor, Limit, require
from ..members import Member
from ._forward import forward
from .bodies import TicketMessageBody, TicketPatchBody

router = APIRouter()
TicketId = Annotated[int, Path(ge=1, le=2**31 - 1)]


@router.get("/tickets")
async def list_tickets(
    request: Request,
    member: Annotated[Member, Depends(require("tickets.read"))],
    status: Optional[Literal["open", "waiting_on_us", "waiting_on_user", "resolved", "closed"]] = None,
    reason: Annotated[Optional[str], Query(pattern=r"^[a-z_]{1,40}$")] = None,
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None,
    # "me", "none" (unassigned) or a staff email
    assignee: Annotated[Optional[str], Query(max_length=254, pattern=r"^(me|none|[^\s@]+@[^\s@]+)$")] = None,
    q: Annotated[Optional[str], Query(max_length=200)] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    query = {
        "status": status,
        "reason": reason,
        "priority": priority,
        "assignee": member.email if assignee == "me" else assignee,
        "q": q.strip() if q else None,
        "cursor": cursor,
        "limit": limit,
    }
    return await forward(request, "GET", f"{API}/tickets", member, query=query, shape=C.TicketList)


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    request: Request, ticket_id: TicketId, member: Annotated[Member, Depends(require("tickets.read"))]
):
    return await forward(request, "GET", f"{API}/tickets/{seg(ticket_id)}", member, shape=C.TicketDetail)


@router.post("/tickets/{ticket_id}/messages")
async def add_message(
    request: Request,
    ticket_id: TicketId,
    body: TicketMessageBody,
    member: Annotated[Member, Depends(require("tickets.write"))],
):
    return await forward(
        request,
        "POST",
        f"{API}/tickets/{seg(ticket_id)}/messages",
        member,
        body=body.model_dump(mode="json"),
        shape=C.TicketMessage,
    )


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    request: Request,
    ticket_id: TicketId,
    body: TicketPatchBody,
    member: Annotated[Member, Depends(require("tickets.write"))],
):
    # Only the fields that were sent: an absent assignee is "keep", a null one is "unassign".
    changes = body.model_dump(mode="json", exclude_unset=True)
    return await forward(request, "PATCH", f"{API}/tickets/{seg(ticket_id)}", member, body=changes, shape=C.TicketRow)
