"""Forwarding helpers for the route modules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..members import Member
from ..shape import prune


async def forward(
    request: Request,
    method: str,
    path: str,
    member: Member,
    *,
    shape: type[BaseModel],
    query: Optional[Mapping[str, Any]] = None,
    body: Any = None,
) -> JSONResponse:
    """One admin API call; only the fields `shape` (a contract model) names come back."""
    data = await request.app.state.admin.call(method, path, actor=member, query=query, body=body)
    return JSONResponse(prune(data, shape, f"{method} {path}"))
