"""Plans: the list, and (owner) creating and editing them."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from .. import contract as C
from ..admin_client import seg
from ..deps import API, require
from ..members import Member
from ._forward import forward
from .bodies import PlanCreateBody, PlanPatchBody

router = APIRouter()
PlanIdPath = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]


@router.get("/plans")
async def list_plans(request: Request, member: Annotated[Member, Depends(require("plans.read"))]):
    return await forward(request, "GET", f"{API}/plans", member, shape=C.PlanList)


@router.post("/plans")
async def create_plan(
    request: Request, body: PlanCreateBody, member: Annotated[Member, Depends(require("plans.write"))]
):
    return await forward(request, "POST", f"{API}/plans", member, body=body.model_dump(mode="json"), shape=C.Plan)


@router.patch("/plans/{plan_id}")
async def update_plan(
    request: Request,
    plan_id: PlanIdPath,
    body: PlanPatchBody,
    member: Annotated[Member, Depends(require("plans.write"))],
):
    changes = body.model_dump(mode="json", exclude_unset=True)
    return await forward(request, "PATCH", f"{API}/plans/{seg(plan_id)}", member, body=changes, shape=C.Plan)
