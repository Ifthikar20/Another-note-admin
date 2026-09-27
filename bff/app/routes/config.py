"""
The Settings page (owner): who the admin members are, the price table in force, and the
access review.

Members are read from this BFF's configuration (ADMIN_MEMBERS) in this phase; editing
them here comes later. Prices live in the backend (app/core/usage_prices.py and the
USAGE_PRICES_JSON override), so they come from the admin API.

The access review is the evidence a periodic review of admin access needs (SOC 2 CC6.2,
CC6.3): every member, their role and what it allows, and their last recorded admin
action (from the audit log), as a page and as a CSV to sign off and file.
"""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import UTC, datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from .. import contract as C
from ..admin_client import AdminApiError
from ..deps import API, require
from ..members import ROLES, Member
from ..shape import prune
from ._forward import forward
from .audit import csv_cell

router = APIRouter()
Owner = Annotated[Member, Depends(require("settings.read"))]


def _listed(request: Request) -> list[Member]:
    settings = request.app.state.settings
    members = [Member(email, role) for email, role in settings.members.items()]
    if settings.dev_identity and settings.dev_identity.email not in settings.members:
        members.append(settings.dev_identity)
    return sorted(members, key=lambda m: (ROLES.index(m.role), m.email))


@router.get("/settings/members")
async def members(request: Request, member: Owner) -> JSONResponse:
    settings = request.app.state.settings
    listed = sorted(settings.members.items(), key=lambda item: (ROLES.index(item[1]), item[0]))
    return JSONResponse(
        {
            "items": [{"email": email, "role": role} for email, role in listed],
            "source": "ADMIN_MEMBERS",
            "editable": False,
            "dev_identity": (
                {"email": settings.dev_identity.email, "role": settings.dev_identity.role}
                if settings.dev_identity
                else None
            ),
        }
    )


@router.get("/settings/prices")
async def prices(request: Request, member: Owner):
    return await forward(request, "GET", f"{API}/usage/prices", member, shape=C.Prices)


async def _last_action(request: Request, reviewer: Member, email: str) -> tuple[Optional[str], Optional[str]]:
    """The time and action of this member's most recent audit row, if any."""
    try:
        data = await request.app.state.admin.call(
            "GET", f"{API}/audit", actor=reviewer, query={"actor": email, "limit": 1}
        )
    except AdminApiError:
        return None, None
    items = prune(data, C.AuditList).get("items") or []
    if not items:
        return None, None
    return items[0].get("at"), items[0].get("action")


async def _review(request: Request, reviewer: Member) -> dict[str, Any]:
    listed = _listed(request)
    semaphore = asyncio.Semaphore(4)

    async def one(m: Member) -> tuple[Optional[str], Optional[str]]:
        async with semaphore:
            return await _last_action(request, reviewer, m.email)

    last = await asyncio.gather(*(one(m) for m in listed))
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "generated_by": reviewer.email,
        "items": [
            {
                "email": m.email,
                "role": m.role,
                "capabilities": m.capabilities,
                "last_admin_action_at": at,
                "last_admin_action": action,
                "dev_identity": request.app.state.settings.dev_identity == m,
            }
            for m, (at, action) in zip(listed, last, strict=False)
        ],
        "sources": [
            "ADMIN_MEMBERS (who this app lets in, and with which role)",
            "the Cloudflare Access policy for the admin hostname (who can reach it at all)",
        ],
    }


@router.get("/settings/access-review")
async def access_review(request: Request, member: Owner) -> JSONResponse:
    return JSONResponse(await _review(request, member))


@router.get("/settings/access-review.csv")
async def access_review_csv(request: Request, member: Owner) -> Response:
    review = await _review(request, member)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(
        [
            "email",
            "role",
            "capabilities",
            "last_admin_action_at",
            "last_admin_action",
            "generated_at",
            "generated_by",
            "decision (keep / change / remove)",
            "reviewer notes",
        ]
    )
    for item in review["items"]:
        writer.writerow(
            [
                csv_cell(item["email"]),
                csv_cell(item["role"]),
                csv_cell(" ".join(item["capabilities"])),
                csv_cell(item["last_admin_action_at"]),
                csv_cell(item["last_admin_action"]),
                csv_cell(review["generated_at"]),
                csv_cell(review["generated_by"]),
                "",
                "",
            ]
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="anothernote-admin-access-review-{stamp}.csv"'},
    )
