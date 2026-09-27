"""
The admin API's responses, as this app expects them (build specification 5.8.4 and
Appendix B, filled in where the specification gives only an example).

This is the contract between the admin app and the admin API that phase 2 builds in
playstudy-backend. It is used twice:

  - the BFF forwards only the fields named here (shape.py prunes everything else), so
    even a mistake in the admin API cannot put an unnamed field on a staff member's screen;
  - the stand-in admin API (devstub/) builds its answers from these models, which forbid
    extra fields, as section 3.3 asks of the real one.

Where this goes beyond Appendix B (the `profile` and `activity_30d` blocks of a person's
page, `status` on a user row, the ticket counts, `month_to_date`, GET /usage/prices and
the analytics endpoints), docs/ADMIN_API_CONTRACT.md says so.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["standard", "managed_child"]
AgeBand = Literal["under_13", "13_17", "18_plus", "unknown"]
UserStatus = Literal["active", "deactivated", "deleted"]
PlanSource = Literal["user", "organization", "default"]
AssignmentStatus = Literal["active", "trial", "past_due", "canceled", "expired"]
AssignmentSource = Literal["manual", "promo", "organization", "stripe"]
TicketStatus = Literal["open", "waiting_on_us", "waiting_on_user", "resolved", "closed"]
TicketPriority = Literal["low", "normal", "high", "urgent"]
AuthKind = Literal[
    "sign_in",
    "sign_in_failed",
    "pin_locked",
    "pin_reset",
    "sign_out",
    "sign_out_everywhere",
    "password_changed",
    "refresh_replay",
    "admin_action",
]
AuthMethod = Literal["password", "google", "microsoft", "pin", "desktop"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Page(Model):
    next_cursor: Optional[str] = None


class Range(Model):
    from_: date = Field(alias="from")
    to: date
    tz: Literal["UTC"] = "UTC"


# --- health ---------------------------------------------------------------------------
class Health(Model):
    ok: bool
    db: bool
    redis: bool
    version: str


# --- overview and metrics (B.1) -------------------------------------------------------
class Accounts(Model):
    total: int
    adults: int  # standard accounts (not child profiles)
    children: int  # managed child profiles
    teachers: int
    guardians: int
    deactivated: int


class Activity(Model):
    online_now: int
    active_today: int
    active_7d: int
    active_30d: int


class SignInsToday(Model):
    today: int
    failed_today: int
    by_method_today: dict[str, int]


class Sessions(Model):
    live: int
    users_with_live_sessions: int


class FeatureCost(Model):
    feature: str
    cost_usd: Optional[float]
    tokens: int


class OverviewUsage(Model):
    tokens_today: int
    cost_today_usd: Optional[float]
    cost_month_usd: Optional[float]
    budget_month_usd: Optional[float]
    top_features_month: list[FeatureCost]


class OverviewTickets(Model):
    open: int
    waiting_on_us: int
    oldest_open_hours: Optional[float]


class Storage(Model):
    pdfs: int
    pdf_bytes: int


class Overview(Model):
    range: Range
    accounts: Accounts
    activity: Activity
    sign_ins: SignInsToday
    sessions: Sessions
    usage: OverviewUsage
    tickets: OverviewTickets
    storage: Storage
    generated_at: datetime


class DauPoint(Model):
    day: date
    dau: int


class ActiveUsers(Model):
    range: Range
    granularity: Literal["day"]
    series: list[DauPoint]
    wau: int
    mau: int
    as_of: date


class SignInPoint(Model):
    day: date
    method: str
    count: int


class DayCount(Model):
    day: date
    count: int


class SignInTotals(Model):
    sign_ins: int
    failures: int


class SignIns(Model):
    range: Range
    group: Literal["method"]
    series: list[SignInPoint]
    failures: list[DayCount]
    totals: SignInTotals


class OnlineNow(Model):
    online_now: int
    live_sessions: int
    users_with_live_sessions: int
    generated_at: datetime


# --- people (B.2, B.3) ---------------------------------------------------------------
class Identity(Model):
    email_masked: Optional[str]
    username_masked: Optional[str]
    first_name: str


class UserRef(Model):
    id: int
    identity: Identity
    kind: Kind


class OrgRef(Model):
    id: int
    name: str


class PlanRef(Model):
    id: str
    name: str
    source: PlanSource
    status: str


class Usage30d(Model):
    tokens: int
    cost_usd: Optional[float]


class UserRow(Model):
    id: int
    identity: Identity
    kind: Kind
    role: Optional[str]
    age_band: AgeBand
    organization: Optional[OrgRef]
    plan: Optional[PlanRef]
    created_at: datetime
    last_login: Optional[datetime]
    last_seen_at: Optional[datetime]
    live_sessions: int
    usage_30d: Usage30d
    open_tickets: int
    status: UserStatus
    # deactivated, deleted, locked (PIN), demo, child, child_linked (has a guardian)
    flags: list[str]


class UserList(Page):
    items: list[UserRow]


class Profile(Model):
    auth_provider: Optional[str]
    org_role: Optional[str]
    onboarding_completed: bool
    credentials_locked: bool
    pin_locked_until: Optional[datetime]
    xp: int
    deleted_at: Optional[datetime]
    is_demo: bool
    email_domain: Optional[str]


class Footprint(Model):
    """Counts and sizes only: never a title, never a word of what was written."""

    study_sessions: int
    notes: int
    youtube_sessions: int
    pdfs: int
    office_files: int
    pdf_bytes: int
    highlights: int
    sticky_notes: int
    answers: int
    last_session_at: Optional[datetime]


class FamilyLink(Model):
    id: int
    relation: Literal["guardian", "child"]  # what the other account is to this one
    other_user_id: int
    origin: Literal["created", "claimed"]
    status: Literal["pending", "active", "revoked", "aged_out"]
    activated_at: Optional[datetime]
    revoked_at: Optional[datetime]


class Family(Model):
    guardians_active: int
    guardians_revoked: int
    children_active: int
    children_revoked: int
    links: list[FamilyLink]


class UserSecurity(Model):
    failed_sign_ins_30d: int
    locked_until: Optional[datetime]
    replays_30d: int


class FeatureUsage(Model):
    feature: str
    tokens: int
    cost_usd: Optional[float]


class ActiveDay(Model):
    day: date
    active_seconds: int


class UserDetail(Model):
    user: UserRow
    profile: Profile
    footprint: Footprint
    family: Family
    security: UserSecurity
    usage_by_feature_30d: list[FeatureUsage]
    activity_30d: list[ActiveDay]
    note: str


class RevealedEmail(Model):
    email: Optional[str]
    first_name: str


class SessionDevice(Model):
    ua_family: Optional[str]
    country: Optional[str]
    method: Optional[AuthMethod]
    last_refresh_at: Optional[datetime]


class LiveSession(Model):
    session_id: int
    created_at: datetime
    expires_at: datetime
    device: Optional[SessionDevice]


class SessionList(Page):
    items: list[LiveSession]


class SignOutResult(Model):
    sessions_ended: int


class ActiveResult(Model):
    is_active: bool


# --- usage and cost -------------------------------------------------------------------
class UsageNumbers(Model):
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    characters: int
    audio_ms: int
    cost_usd: Optional[float]  # null when no call in it had a known price
    unpriced_calls: int  # calls whose price was unknown when they were made


class UsageRow(UsageNumbers):
    key: str


class UsagePoint(Model):
    day: date
    key: str
    calls: int
    tokens: int
    characters: int
    audio_ms: int
    cost_usd: Optional[float]


class MonthToDate(Model):
    month: str
    cost_usd: Optional[float]
    budget_usd: Optional[float]


class UsageSummary(Model):
    range: Range
    group: Literal["day", "feature", "provider", "model"]
    totals: UsageNumbers
    rows: list[UsageRow]
    series: list[UsagePoint]
    month_to_date: Optional[MonthToDate] = None


class TopUser(Model):
    user: UserRef
    value: float
    calls: int
    tokens: int
    characters: int
    cost_usd: Optional[float]


class TopUsers(Model):
    range: Range
    metric: Literal["cost", "tokens", "characters"]
    items: list[TopUser]


class Anomaly(Model):
    user: UserRef
    metric: Literal["tokens", "cost"]
    value: float
    median_30d: float
    ratio: Optional[float]
    reason: Literal["spike", "over_plan_share"]
    plan_id: Optional[str]


class Anomalies(Model):
    date: date
    items: list[Anomaly]


class Price(Model):
    provider: str
    model: str
    input_per_mtok: Optional[float]
    output_per_mtok: Optional[float]
    cache_read_per_mtok: Optional[float]
    cache_write_per_mtok: Optional[float]
    per_mchar: Optional[float]
    per_request: Optional[float]


class Prices(Model):
    items: list[Price]
    source: str
    currency: Literal["USD"] = "USD"
    budget_month_usd: Optional[float]


# --- plans ---------------------------------------------------------------------------
class PlanLimits(Model):
    monthly_ai_tokens: Optional[int] = None
    monthly_ai_cost_usd: Optional[float] = None
    monthly_tts_characters: Optional[int] = None
    monthly_transcription_minutes: Optional[int] = None
    max_upload_mb: Optional[int] = None
    max_study_sessions: Optional[int] = None
    teach_mode: Optional[bool] = None
    pictures: Optional[bool] = None
    youtube_import: Optional[bool] = None
    family_seats: Optional[int] = None


class AssignmentCounts(Model):
    active: int
    trial: int


class Plan(Model):
    id: str
    name: str
    description: str
    is_default: bool
    is_active: bool
    limits: PlanLimits
    price_cents: Optional[int]
    currency: Optional[str]
    interval: Optional[Literal["month", "year"]]
    created_at: datetime
    updated_at: datetime
    assignments: AssignmentCounts


class PlanList(Model):
    items: list[Plan]


class Assignment(Model):
    id: int
    subject_type: Literal["user", "organization"]
    subject_id: int
    plan_id: str
    status: AssignmentStatus
    source: AssignmentSource
    starts_at: datetime
    ends_at: Optional[datetime]
    note: Optional[str]
    assigned_by: Optional[str]
    created_at: datetime


class PlanName(Model):
    id: str
    name: str


class EffectivePlan(Model):
    plan: PlanName
    source: PlanSource
    status: str
    assignment_id: Optional[int]
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]


class SubjectPlan(Model):
    effective: EffectivePlan
    history: list[Assignment]


# --- organisations --------------------------------------------------------------------
class OrgRow(Model):
    id: int
    name: str
    slug: str
    sso_provider: Optional[str]
    sso_enforced: bool
    created_at: datetime
    members: int
    plan: Optional[PlanRef]


class OrgList(Page):
    items: list[OrgRow]


class OrgDomain(Model):
    domain: str
    verified: bool


class OrgMemberCounts(Model):
    total: int
    teachers: int
    students: int
    org_owners: int
    org_admins: int


class OrgDetail(Model):
    org: OrgRow
    domains: list[OrgDomain]
    member_counts: OrgMemberCounts
    plan: SubjectPlan


# --- tickets --------------------------------------------------------------------------
class TicketRow(Model):
    id: int
    number: str
    reason: str
    reason_label: str
    subject: str
    status: TicketStatus
    priority: TicketPriority
    assignee_email: Optional[str]
    tags: list[str]
    user: UserRef
    created_at: datetime
    updated_at: datetime
    last_user_at: Optional[datetime]
    last_staff_at: Optional[datetime]
    message_count: int
    preview: str  # the start of the latest message the person can see


class TicketCounts(Model):
    open: int
    waiting_on_us: int
    waiting_on_user: int
    resolved: int
    closed: int


class TicketList(Page):
    items: list[TicketRow]
    counts: TicketCounts


class TicketContext(Model):
    browser: Optional[str] = None
    language: Optional[str] = None
    viewport: Optional[str] = None
    timezone: Optional[str] = None
    app_version: Optional[str] = None
    session_id: Optional[str] = None
    from_: Optional[str] = Field(None, alias="from")


class TicketMessage(Model):
    id: int
    author: Literal["user", "staff", "system"]
    staff_email: Optional[str]
    body: str
    internal: bool
    created_at: datetime


class TicketUser(Model):
    id: int
    identity: Identity
    kind: Kind
    organization: Optional[OrgRef]
    plan: Optional[PlanRef]
    last_seen_at: Optional[datetime]
    usage_30d: Usage30d


class TicketDetail(Model):
    ticket: TicketRow
    page_url: Optional[str]
    context: Optional[TicketContext]
    closed_at: Optional[datetime]
    messages: list[TicketMessage]
    user: TicketUser


class OutboxEvent(Model):
    id: int
    kind: Literal["ticket.created", "ticket.user_replied"]
    ticket_id: int
    created_at: datetime


class EventList(Page):
    items: list[OutboxEvent]


# --- security -------------------------------------------------------------------------
class AuthEvent(Model):
    id: int
    created_at: datetime
    user_id: Optional[int]
    kind: AuthKind
    method: Optional[AuthMethod]
    reason: Optional[str]
    country: Optional[str]
    ua_family: Optional[str]
    ip_prefix_hash: Optional[str]
    identifier_hash: Optional[str]


class AuthEventList(Page):
    items: list[AuthEvent]


class SecurityTotals(Model):
    sign_ins: int
    failed: int
    lockouts: int
    replays: int
    pin_resets: int
    sign_outs_everywhere: int


class HourCount(Model):
    hour: datetime
    count: int


class ReasonCount(Model):
    reason: str
    count: int


class Network(Model):
    ip_prefix_hash: str
    failures: int
    identifiers: int
    countries: list[str]
    last_at: datetime


class SecuritySummary(Model):
    range: Range
    totals: SecurityTotals
    failed_per_hour: list[HourCount]
    failures_by_reason: list[ReasonCount]
    top_networks: list[Network]


# --- audit ----------------------------------------------------------------------------
Detail = Union[str, int, float, bool, None, list[Union[str, int]]]


class AuditRow(Model):
    id: int
    at: datetime
    actor_email: str
    actor_role: str
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    reason: Optional[str]
    request_id: Optional[str]
    details: Optional[dict[str, Detail]]


class AuditList(Page):
    items: list[AuditRow]


# --- analytics: what people did in the app, and what went wrong (admin_analytics_v) ----
# Only the view's columns: kind, name (at most 160 characters; an error's message), path,
# and the three utm_* tags. Never `data` (stacks), the user agent, the browser and visit
# ids, or any other tag.
AnalyticsKind = Literal["view", "action", "error"]


class AnalyticsDay(Model):
    day: date
    view: int
    action: int
    error: int


class NameCount(Model):
    name: str
    count: int
    users: int  # distinct signed-in people


class Campaign(Model):
    utm_source: Optional[str]
    utm_medium: Optional[str]
    utm_campaign: Optional[str]
    events: int
    users: int


class AnalyticsTotals(Model):
    views: int
    actions: int
    errors: int
    users: int


class AnalyticsSummary(Model):
    range: Range
    totals: AnalyticsTotals
    by_day: list[AnalyticsDay]
    top_pages: list[NameCount]
    top_actions: list[NameCount]
    campaigns: list[Campaign]


class ErrorGroup(Model):
    """One thing that went wrong, grouped by its message."""

    name: str
    count: int
    users: int
    first_at: datetime
    last_at: datetime
    paths: list[str]  # up to five pages it happened on
    by_day: list[DayCount]


class ErrorGroups(Page):
    range: Range
    items: list[ErrorGroup]


class AnalyticsEvent(Model):
    id: int
    created_at: datetime
    user_id: Optional[int]
    kind: AnalyticsKind
    name: str
    path: Optional[str]
    utm_source: Optional[str]
    utm_medium: Optional[str]
    utm_campaign: Optional[str]


class AnalyticsEventList(Page):
    items: list[AnalyticsEvent]


class ErrorBody(Model):
    code: Literal["not_found", "forbidden", "invalid", "conflict", "unavailable", "unauthorized"]
    message: str


class Error(Model):
    error: ErrorBody


def dump(model: BaseModel) -> Any:
    """What goes on the wire: aliases (`from`), JSON types."""
    return model.model_dump(mode="json", by_alias=True)
