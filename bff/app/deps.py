"""
What the route modules share: who is asking, what they may do, and the admin client.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Annotated, Any, Optional

from fastapi import Depends, HTTPException, Query, Request

from .admin_client import AdminClient
from .members import CAPABILITIES, Member

API = "/admin/v1"

# Query parameters used across pages. `from` is a keyword in Python, hence the alias.
FromDate = Annotated[Optional[date], Query(alias="from")]
ToDate = Annotated[Optional[date], Query(alias="to")]
Cursor = Annotated[Optional[str], Query(max_length=512, pattern=r"^[A-Za-z0-9_\-=.~]+$")]
Limit = Annotated[int, Query(ge=1, le=100)]
Email = Annotated[Optional[str], Query(max_length=254, pattern=r"^[^\s@]+@[^\s@]+$")]


def current_member(request: Request) -> Member:
    member = request.scope.get("state", {}).get("member")
    if not isinstance(member, Member):  # the Gatekeeper sets it; never reached without it
        raise HTTPException(status_code=401)
    return member


def require(capability: str) -> Callable[..., Member]:
    """A dependency: the member, if their role has `capability` (5.8.3), else 403."""
    if capability not in CAPABILITIES:
        raise KeyError(capability)

    def dependency(member: Annotated[Member, Depends(current_member)]) -> Member:
        if not member.can(capability):
            raise HTTPException(status_code=403, detail="Your role cannot do this.")
        return member

    dependency.__name__ = f"require_{capability.replace('.', '_')}"
    return dependency


def admin(request: Request) -> AdminClient:
    return request.app.state.admin


def dates(from_: Optional[date], to: Optional[date]) -> dict[str, Any]:
    if from_ and to and from_ > to:
        raise HTTPException(status_code=400, detail="The start of the range is after its end.")
    return {"from": from_.isoformat() if from_ else None, "to": to.isoformat() if to else None}


def page(cursor: Optional[str], limit: Optional[int]) -> Mapping[str, Any]:
    return {"cursor": cursor, "limit": limit}
