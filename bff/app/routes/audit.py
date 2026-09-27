"""The Audit page (owner): every admin action, and a CSV export of the audit log only."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from .. import contract as C
from ..deps import API, Cursor, Email, FromDate, Limit, ToDate, dates, require
from ..members import Member
from ..shape import prune
from ._forward import forward

router = APIRouter()
Owner = Annotated[Member, Depends(require("audit.read"))]

# The actions of 5.6 (view.overview, user.reveal_email, ticket.reply, ...). A pattern rather
# than a fixed list, so an action the admin API adds can still be filtered on.
Action = Annotated[Optional[str], Query(max_length=60, pattern=r"^[a-z_]+\.[a-z_]+$")]
# Actions to leave out, comma separated: the live ticket stream's requests (view.events)
# are audited like any other, and would otherwise bury the rest.
Exclude = Annotated[Optional[str], Query(max_length=300, pattern=r"^[a-z_]+\.[a-z_]+(,[a-z_]+\.[a-z_]+)*$")]

EXPORT_PAGE = 100
EXPORT_MAX_PAGES = 50  # 5,000 rows; narrow the range for more
COLUMNS = ("at", "actor_email", "actor_role", "action", "target_type", "target_id", "reason", "request_id", "details")


@router.get("/audit")
async def audit_log(
    request: Request,
    member: Owner,
    actor: Email = None,
    action: Action = None,
    exclude: Exclude = None,
    from_: FromDate = None,
    to: ToDate = None,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    query = {"actor": actor, "action": action, "exclude": exclude, **dates(from_, to), "cursor": cursor, "limit": limit}
    return await forward(request, "GET", f"{API}/audit", member, query=query, shape=C.AuditList)


def csv_cell(value: Any) -> str:
    """A cell a spreadsheet will show as text, never run as a formula."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        text = "'" + text
    return text


@router.get("/audit/export.csv")
async def export(
    request: Request,
    member: Owner,
    actor: Email = None,
    action: Action = None,
    exclude: Exclude = None,
    from_: FromDate = None,
    to: ToDate = None,
) -> Response:
    rows: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    for _ in range(EXPORT_MAX_PAGES):
        query = {
            "actor": actor,
            "action": action,
            "exclude": exclude,
            **dates(from_, to),
            "cursor": cursor,
            "limit": EXPORT_PAGE,
        }
        data = prune(await request.app.state.admin.call("GET", f"{API}/audit", actor=member, query=query), C.AuditList)
        rows.extend(item for item in data.get("items", []) if isinstance(item, dict))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([csv_cell(row.get(column)) for column in COLUMNS])
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(
        # A byte-order mark so spreadsheet programs read UTF-8 as UTF-8.
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="anothernote-admin-audit-{stamp}.csv"',
            "X-Export-Rows": str(len(rows)),
            "X-Export-Truncated": "1" if cursor else "0",
        },
    )
