"""
What the browser may send with a change. Checked here before anything is forwarded:
unknown fields are refused (extra="forbid"), and each field is bounded.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
PlanId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")]


def _lower(value: object) -> object:
    # Before the pattern is checked (a StringConstraints to_lower runs after it).
    return value.strip().lower() if isinstance(value, str) else value


Tag = Annotated[str, BeforeValidator(_lower), StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")]
EmailStr = Annotated[str, BeforeValidator(_lower), StringConstraints(max_length=254, pattern=r"^[^\s@]+@[^\s@]+$")]

TICKET_STATUSES = ("open", "waiting_on_us", "waiting_on_user", "resolved", "closed")
TICKET_PRIORITIES = ("low", "normal", "high", "urgent")


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReasonBody(Body):
    reason: Reason


class RevealEmailBody(Body):
    reason: Reason
    ticket_id: Optional[int] = Field(None, ge=1)


class TicketMessageBody(Body):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)]
    internal: bool = False


class TicketPatchBody(Body):
    status: Optional[Literal["open", "waiting_on_us", "waiting_on_user", "resolved", "closed"]] = None
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    # null unassigns; leave the field out to keep the assignee
    assignee_email: Optional[EmailStr] = None
    tags: Optional[list[Tag]] = Field(None, max_length=10)

    @field_validator("tags")
    @classmethod
    def _unique(cls, tags: Optional[list[str]]) -> Optional[list[str]]:
        return list(dict.fromkeys(tags)) if tags is not None else None


class PlanLimits(Body):
    """Every limit optional; null means unlimited (5.4.1)."""

    monthly_ai_tokens: Optional[int] = Field(None, ge=0)
    monthly_ai_cost_usd: Optional[float] = Field(None, ge=0)
    monthly_tts_characters: Optional[int] = Field(None, ge=0)
    monthly_transcription_minutes: Optional[int] = Field(None, ge=0)
    max_upload_mb: Optional[int] = Field(None, ge=0)
    max_study_sessions: Optional[int] = Field(None, ge=0)
    teach_mode: Optional[bool] = None
    pictures: Optional[bool] = None
    youtube_import: Optional[bool] = None
    family_seats: Optional[int] = Field(None, ge=0)


class PlanCreateBody(Body):
    id: PlanId
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    is_active: bool = True
    is_default: bool = False
    limits: PlanLimits = Field(default_factory=PlanLimits)
    price_cents: Optional[int] = Field(None, ge=0)
    currency: Optional[Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]] = None
    interval: Optional[Literal["month", "year"]] = None


class PlanPatchBody(Body):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]] = None
    description: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    limits: Optional[PlanLimits] = None
    price_cents: Optional[int] = Field(None, ge=0)
    currency: Optional[Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]] = None
    interval: Optional[Literal["month", "year"]] = None


class PlanAssignBody(Body):
    plan_id: PlanId
    status: Literal["active", "trial", "canceled"] = "active"
    ends_at: Optional[datetime] = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
