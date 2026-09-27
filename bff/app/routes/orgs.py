"""Organisations: member counts, SSO settings, and their plan."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query, Request

from .. import contract as C
from ..admin_client import seg
from ..deps import API, Cursor, Limit, require
from ..members import Member
from ._forward import forward
from .bodies import PlanAssignBody

router = APIRouter()
OrgId = Annotated[int, Path(ge=1, le=2**31 - 1)]


@router.get("/orgs")
async def list_orgs(
    request: Request,
    member: Annotated[Member, Depends(require("orgs.read"))],
    q: Annotated[Optional[str], Query(max_length=120)] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    query = {"q": q.strip() if q else None, "cursor": cursor, "limit": limit}
    return await forward(request, "GET", f"{API}/orgs", member, query=query, shape=C.OrgList)


@router.get("/orgs/{org_id}")
async def get_org(request: Request, org_id: OrgId, member: Annotated[Member, Depends(require("orgs.read"))]):
    return await forward(request, "GET", f"{API}/orgs/{seg(org_id)}", member, shape=C.OrgDetail)


@router.put("/orgs/{org_id}/plan")
async def put_org_plan(
    request: Request, org_id: OrgId, body: PlanAssignBody, member: Annotated[Member, Depends(require("plans.write"))]
):
    return await forward(
        request, "PUT", f"{API}/orgs/{seg(org_id)}/plan", member, body=body.model_dump(mode="json"), shape=C.Assignment
    )
