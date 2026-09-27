"""
A stand-in for the internal admin API (build specification 5.8), for local development
and this repository's tests, until phase 2 builds the real one in playstudy-backend.

It speaks the contract the admin app expects (schemas.py) over made-up data (data.py),
and checks requests the way the real one must: the service token, the clock (60 s), the
HMAC signature over method, path, time, actor, role, request id and body, and request ids
seen in the last 5 minutes (5.8.2); then the role table (5.8.3). Every request writes one
audit row, failures included. It is never part of the production image.

    ADMIN_SERVICE_TOKEN=... ADMIN_SIGNING_KEY=... uvicorn devstub.app:app --port 8001

STUB_LIVE_EVENTS=1 makes a new ticket or reply every STUB_LIVE_INTERVAL seconds (45) and
keeps people "online", so the live badge and Online now have something to show.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import random
import re
import time
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from bff.app import contract as S

from .data import (
    BUDGET_MONTH_USD,
    PRICES,
    REASON_LABELS,
    TICKETS,
    Assignment,
    Audit,
    AuthEvent,
    Event,
    Message,
    Outbox,
    Plan,
    Store,
    Ticket,
    UsageDay,
    User,
    masked_email,
    masked_username,
)

UTC = UTC
VERSION = "devstub-0.1.0"
SKEW_SECONDS = 60
REPLAY_SECONDS = 300
ROLES = ("owner", "support", "analyst", "viewer")
ALL = set(ROLES)
SUPPORT_UP = {"owner", "support"}
TICKET_READERS = {"owner", "support", "viewer"}
OWNER = {"owner"}
NOTE = "Study content is never shown in the admin app."


# --- request checking (5.8.2), written independently of the BFF's signing code --------
class Replay:
    def __init__(self) -> None:
        self._seen: dict[str, float] = {}

    def first_time(self, request_id: str) -> bool:
        now = time.monotonic()
        for rid, at in list(self._seen.items()):
            if now - at > REPLAY_SECONDS:
                del self._seen[rid]
        if request_id in self._seen:
            return False
        self._seen[request_id] = now
        return True


def problem_with(
    scope: dict[str, Any], headers: dict[str, str], body: bytes, token: str, key: str, replay: Replay
) -> Optional[str]:
    """Why a request must be refused (401), or None if it is signed correctly."""
    auth = headers.get("authorization", "")
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:].encode(), token.encode()):
        return "wrong service token"
    needed = ("x-admin-actor", "x-admin-role", "x-admin-request-id", "x-admin-timestamp", "x-admin-signature")
    if any(not headers.get(h) for h in needed):
        return "missing admin headers"
    stamp = headers["x-admin-timestamp"]
    if not stamp.isdigit() or abs(time.time() - int(stamp)) > SKEW_SECONDS:
        return "timestamp too far from now"
    raw_path = scope.get("raw_path") or scope["path"].encode()
    target = raw_path.split(b"?", 1)[0].decode("latin-1")
    if scope.get("query_string"):
        target += "?" + scope["query_string"].decode("latin-1")
    message = "\n".join(
        [
            scope["method"].upper(),
            target,
            stamp,
            headers["x-admin-actor"],
            headers["x-admin-role"],
            headers["x-admin-request-id"],
            hashlib.sha256(body).hexdigest(),
        ]
    ).encode()
    expected = base64.urlsafe_b64encode(hmac.new(key.encode(), message, hashlib.sha256).digest()).decode().rstrip("=")
    if not hmac.compare_digest(headers["x-admin-signature"].rstrip("="), expected):
        return "bad signature"
    if not replay.first_time(headers["x-admin-request-id"]):
        return "request id already used"
    if headers["x-admin-role"] not in ROLES:
        return "unknown role"
    return None


class Actor(BaseModel):
    email: str
    role: str
    request_id: str


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(S.dump(S.Error(error=S.ErrorBody(code=code, message=message))), status_code=status)


# --- audit: one row per request, written when the response starts ---------------------
AUDIT_RULES: list[tuple[str, re.Pattern[str], str, Optional[str]]] = [
    ("GET", re.compile(r"^/admin/v1/(overview|metrics/.+)$"), "view.overview", None),
    ("GET", re.compile(r"^/admin/v1/users$"), "view.users", None),
    ("POST", re.compile(r"^/admin/v1/users/(\d+)/reveal-email$"), "user.reveal_email", "user"),
    ("POST", re.compile(r"^/admin/v1/users/(\d+)/sign-out-everywhere$"), "user.sign_out_everywhere", "user"),
    ("POST", re.compile(r"^/admin/v1/users/(\d+)/deactivate$"), "user.deactivate", "user"),
    ("POST", re.compile(r"^/admin/v1/users/(\d+)/reactivate$"), "user.reactivate", "user"),
    ("PUT", re.compile(r"^/admin/v1/users/(\d+)/plan$"), "plan.assign", "user"),
    ("GET", re.compile(r"^/admin/v1/users/(\d+)(/.*)?$"), "view.user", "user"),
    ("GET", re.compile(r"^/admin/v1/usage/.+$"), "view.usage", None),
    ("GET", re.compile(r"^/admin/v1/plans$"), "view.plans", None),
    ("POST", re.compile(r"^/admin/v1/plans$"), "plan.create", "plan"),
    ("PATCH", re.compile(r"^/admin/v1/plans/([a-z0-9_-]+)$"), "plan.update", "plan"),
    ("PUT", re.compile(r"^/admin/v1/orgs/(\d+)/plan$"), "plan.assign", "organization"),
    ("GET", re.compile(r"^/admin/v1/orgs(/(\d+))?$"), "view.orgs", "organization"),
    ("GET", re.compile(r"^/admin/v1/tickets$"), "view.tickets", None),
    ("GET", re.compile(r"^/admin/v1/tickets/(\d+)$"), "ticket.view", "ticket"),
    ("POST", re.compile(r"^/admin/v1/tickets/(\d+)/messages$"), "ticket.reply", "ticket"),
    ("PATCH", re.compile(r"^/admin/v1/tickets/(\d+)$"), "ticket.update", "ticket"),
    ("GET", re.compile(r"^/admin/v1/events(/stream)?$"), "view.events", None),
    ("GET", re.compile(r"^/admin/v1/security/.+$"), "view.security", None),
    ("GET", re.compile(r"^/admin/v1/analytics/.+$"), "view.activity", None),
    ("GET", re.compile(r"^/admin/v1/audit$"), "audit.view", None),
]


def audit_for(method: str, path: str) -> Optional[tuple[str, Optional[str], Optional[str]]]:
    for m, pattern, action, target_type in AUDIT_RULES:
        match = pattern.match(path)
        if m == method and match:
            target_id = next((g for g in match.groups() if g and not g.startswith("/")), None)
            return action, (target_type if target_id else None), target_id
    return None


class Gate:
    """Signed requests only; then one audit row per request."""

    def __init__(self, app: Any, stub: Stub):
        self.app = app
        self.stub = stub

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if len(body) > 1_000_000:
                return await error(413, "invalid", "request too large")(scope, receive, send)
            if not message.get("more_body"):
                break
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        why = problem_with(scope, headers, body, self.stub.token, self.stub.key, self.stub.replay)
        if why:
            self.stub.refusals.append(why)
            return await error(401, "unauthorized", "not signed correctly")(scope, receive, send)
        actor = Actor(
            email=headers["x-admin-actor"], role=headers["x-admin-role"], request_id=headers["x-admin-request-id"]
        )
        scope.setdefault("state", {})["actor"] = actor
        scope["state"]["audit"] = {}
        delivered = False

        async def replay_body() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        async def send_audited(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                self.stub.write_audit(scope, actor, body, message["status"])
            await send(message)

        await self.app(scope, replay_body, send_audited)


# --- the stub -------------------------------------------------------------------------
class Stub:
    def __init__(
        self,
        token: str,
        key: str,
        store: Optional[Store] = None,
        live_events: bool = False,
        live_interval: float = 45.0,
    ):
        self.token = token
        self.key = key
        self.store = store or Store()
        self.replay = Replay()
        self.refusals: list[str] = []
        self.live_events = live_events
        self.live_interval = live_interval
        self.subscribers: set[asyncio.Queue[Outbox]] = set()
        self.rng = random.Random(99)

    def write_audit(self, scope: dict[str, Any], actor: Actor, body: bytes, status: int) -> None:
        found = audit_for(scope["method"], scope["path"])
        if not found:
            return
        action, target_type, target_id = found
        extra = scope.get("state", {}).get("audit", {})
        action = extra.get("action", action)
        if extra.get("target"):
            target_type, target_id = extra["target"]
        reason = None
        if body:
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    reason = payload.get("reason") or payload.get("note")
            except ValueError:
                pass
        details: dict[str, Any] = dict(extra.get("details", {}))
        if status >= 400:
            details["status"] = status
        s = self.store
        s.audit.append(
            Audit(
                s.next_id("audit"),
                s.current(),
                actor.email,
                actor.role,
                action,
                target_type,
                target_id,
                reason if isinstance(reason, str) else None,
                actor.request_id,
                details or None,
            )
        )

    def add_event(self, kind: str, ticket_id: int, when: datetime) -> Outbox:
        event = Outbox(self.store.next_id("outbox"), kind, ticket_id, when)
        self.store.outbox.append(event)
        for queue in list(self.subscribers):
            queue.put_nowait(event)
        return event

    async def live(self) -> None:
        """New tickets and replies now and then, and people coming and going."""
        s, rng = self.store, self.rng
        while True:
            await asyncio.sleep(self.live_interval)
            now = s.current()
            active = [
                u
                for u in s.users.values()
                if u.status == "active" and u.last_seen_at and now - u.last_seen_at < timedelta(days=2)
            ]
            for u in rng.sample(active, min(14, len(active))):
                u.last_seen_at = now - timedelta(seconds=rng.randint(1, 240))
            if rng.random() < 0.5:
                people = [u for u in s.users.values() if u.status == "active" and u.account_kind == "standard"]
                ticket = s._make_ticket(rng.choice(people), rng.choice(TICKETS), now, "open")
                self.add_event("ticket.created", ticket.id, now)
            else:
                waiting = [t for t in s.tickets.values() if t.status == "waiting_on_user"]
                if waiting:
                    t = rng.choice(waiting)
                    t.messages.append(
                        Message(
                            s.next_id("message"),
                            "user",
                            None,
                            rng.choice(
                                [
                                    "Thanks, that worked.",
                                    "It's still happening, sorry.",
                                    "Here's a bit more detail: it happens every time I open the lesson.",
                                ]
                            ),
                            False,
                            now,
                        )
                    )
                    t.status, t.last_user_at, t.updated_at = "waiting_on_us", now, now
                    self.add_event("ticket.user_replied", t.id, now)


def actor_of(request: Request) -> Actor:
    return request.scope["state"]["actor"]


def need(request: Request, roles: set[str]) -> Actor:
    actor = actor_of(request)
    if actor.role not in roles:
        raise HTTPException(403, "Your role cannot do this.")
    return actor


def note_audit(request: Request, **details: Any) -> None:
    request.scope["state"].setdefault("audit", {}).setdefault("details", {}).update(details)


# --- shaping rows ----------------------------------------------------------------------
def age_band(user: User, today: date) -> str:
    if not user.birth_year:
        return "unknown"
    age = today.year - user.birth_year
    return "under_13" if age < 13 else ("13_17" if age < 18 else "18_plus")


def identity(user: User) -> S.Identity:
    return S.Identity(
        email_masked=masked_email(user.email),
        username_masked=masked_username(user.username),
        first_name=user.first_name,
    )


def user_ref(user: User) -> S.UserRef:
    return S.UserRef(id=user.id, identity=identity(user), kind=user.account_kind or "standard")  # type: ignore[arg-type]


def plan_ref(s: Store, user: User) -> S.PlanRef:
    plan, source, assignment = s.effective_plan(user)
    return S.PlanRef(id=plan.id, name=plan.name, source=source, status=assignment.status if assignment else "active")  # type: ignore[arg-type]


def open_tickets(s: Store, user_id: int) -> int:
    return sum(
        1
        for t in s.tickets.values()
        if t.user_id == user_id and t.status in ("open", "waiting_on_us", "waiting_on_user")
    )


def flags(s: Store, user: User) -> list[str]:
    out = []
    if user.status == "deactivated":
        out.append("deactivated")
    if user.status == "deleted":
        out.append("deleted")
    if user.pin_locked_until and user.pin_locked_until > s.current():
        out.append("locked")
    if user.is_demo:
        out.append("demo")
    if user.account_kind == "managed_child":
        out.append("child")
    elif any(link.child_id == user.id and link.status == "active" for link in s.links):
        out.append("child_linked")
    if any(link.guardian_id == user.id and link.status == "active" for link in s.links):
        out.append("guardian")
    return out


def user_row(s: Store, user: User, live_counts: dict[int, int]) -> S.UserRow:
    tokens, cost = s.usage_30d(user.id)
    org = s.org_of(user)
    return S.UserRow(
        id=user.id,
        identity=identity(user),
        kind=user.account_kind or "standard",  # type: ignore[arg-type]
        role=user.role,
        age_band=age_band(user, s.current().date()),  # type: ignore[arg-type]
        organization=S.OrgRef(id=org.id, name=org.name) if org else None,
        plan=plan_ref(s, user),
        created_at=user.created_at,
        last_login=user.last_login,
        last_seen_at=user.last_seen_at,
        live_sessions=live_counts.get(user.id, 0),
        usage_30d=S.Usage30d(tokens=tokens, cost_usd=cost),
        open_tickets=open_tickets(s, user.id),
        status=user.status,  # type: ignore[arg-type]
        flags=flags(s, user),
    )


def live_counts(s: Store) -> dict[int, int]:
    counts: dict[int, int] = {}
    for t in s.live_tokens():
        counts[t.user_id] = counts.get(t.user_id, 0) + 1
    return counts


def ticket_row(s: Store, t: Ticket) -> S.TicketRow:
    visible = [m for m in t.messages if not m.internal]
    preview = visible[-1].body if visible else ""
    return S.TicketRow(
        id=t.id,
        number=t.number,
        reason=t.reason,
        reason_label=REASON_LABELS.get(t.reason, t.reason),
        subject=t.subject,
        status=t.status,
        priority=t.priority,
        assignee_email=t.assignee_email,  # type: ignore[arg-type]
        tags=t.tags,
        user=user_ref(s.users[t.user_id]),
        created_at=t.created_at,
        updated_at=t.updated_at,
        last_user_at=t.last_user_at,
        last_staff_at=t.last_staff_at,
        message_count=len(t.messages),
        preview=preview[:140],
    )


def assignment_model(a: Assignment) -> S.Assignment:
    return S.Assignment(
        id=a.id,
        subject_type=a.subject_type,
        subject_id=a.subject_id,
        plan_id=a.plan_id,
        status=a.status,  # type: ignore[arg-type]
        source=a.source,
        starts_at=a.starts_at,
        ends_at=a.ends_at,
        note=a.note,
        assigned_by=a.assigned_by,  # type: ignore[arg-type]
        created_at=a.created_at,
    )


def auth_model(e: AuthEvent) -> S.AuthEvent:
    return S.AuthEvent(
        id=e.id,
        created_at=e.created_at,
        user_id=e.user_id,
        kind=e.kind,
        method=e.method,
        reason=e.reason,  # type: ignore[arg-type]
        country=e.country,
        ua_family=e.ua_family,
        ip_prefix_hash=e.ip_prefix_hash,
        identifier_hash=e.identifier_hash,
    )


def usd(micro: int) -> float:
    return round(micro / 1e6, 4)


# --- query helpers -----------------------------------------------------------------------
def day_range(s: Store, from_: Optional[date], to: Optional[date], default_days: int = 30) -> tuple[date, date]:
    today = s.current().date()
    to = to or today
    from_ = from_ or (to - timedelta(days=default_days - 1))
    if from_ > to:
        raise HTTPException(400, "The start of the range is after its end.")
    if (to - from_).days > 400:
        raise HTTPException(400, "The range is longer than 400 days.")
    return from_, to


def rng_model(from_: date, to: date) -> S.Range:
    return S.Range(from_=from_, to=to)


def paginate(items: list[Any], cursor: Optional[str], limit: int) -> tuple[list[Any], Optional[str]]:
    offset = 0
    if cursor:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            if not raw.startswith("o:"):
                raise ValueError
            offset = int(raw[2:])
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "That cursor is not valid.") from None
    limit = max(1, min(100, limit))
    page = items[offset : offset + limit]
    more = offset + limit < len(items)
    return page, (base64.urlsafe_b64encode(f"o:{offset + limit}".encode()).decode().rstrip("=") if more else None)


def in_range(when: datetime, from_: date, to: date) -> bool:
    return from_ <= when.date() <= to


def usage_numbers(rows: Iterable[UsageDay]) -> dict[str, Any]:
    n = {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "characters": 0,
        "audio_ms": 0,
        "unpriced_calls": 0,
    }
    cost, known = 0, False
    for r in rows:
        for k in (
            "calls",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "characters",
            "audio_ms",
            "unpriced_calls",
        ):
            n[k] += getattr(r, k)
        if r.cost_micro_usd is not None:
            cost += r.cost_micro_usd
            known = True
    n["cost_usd"] = usd(cost) if known else None
    return n


def summarize(rows: list[UsageDay], group: str, from_: date, to: date) -> S.UsageSummary:
    def key(r: UsageDay) -> str:
        return r.day.isoformat() if group == "day" else getattr(r, group)

    buckets: dict[str, list[UsageDay]] = {}
    points: dict[tuple[date, str], list[UsageDay]] = {}
    for r in rows:
        buckets.setdefault(key(r), []).append(r)
        points.setdefault((r.day, "total" if group == "day" else key(r)), []).append(r)
    out_rows = [S.UsageRow(key=k, **usage_numbers(v)) for k, v in buckets.items()]
    if group == "day":
        out_rows.sort(key=lambda r: r.key)
    else:
        out_rows.sort(key=lambda r: (-(r.cost_usd or 0), -(r.input_tokens + r.output_tokens), r.key))
    series = []
    for (day, k), v in sorted(points.items()):
        n = usage_numbers(v)
        series.append(
            S.UsagePoint(
                day=day,
                key=k,
                calls=n["calls"],
                tokens=n["input_tokens"] + n["output_tokens"],
                characters=n["characters"],
                audio_ms=n["audio_ms"],
                cost_usd=n["cost_usd"],
            )
        )
    return S.UsageSummary(
        range=rng_model(from_, to),
        group=group,
        totals=S.UsageNumbers(**usage_numbers(rows)),
        rows=out_rows,
        series=series,
    )  # type: ignore[arg-type]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReasonIn(Strict):
    reason: str = ""
    ticket_id: Optional[int] = None


class MessageIn(Strict):
    body: str
    internal: bool = False


class TicketPatchIn(Strict):
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_email: Optional[str] = None
    tags: Optional[list[str]] = None


class AssignIn(Strict):
    plan_id: str
    status: str = "active"
    ends_at: Optional[datetime] = None
    note: str = ""


class PlanIn(Strict):
    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    limits: Optional[S.PlanLimits] = None
    price_cents: Optional[int] = None
    currency: Optional[str] = None
    interval: Optional[str] = None


def require_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(400, "a reason is required")
    return reason


# --- the app ---------------------------------------------------------------------------
def create_stub(
    token: str,
    key: str,
    *,
    store: Optional[Store] = None,
    live_events: bool = False,
    live_interval: float = 45.0,
    heartbeat: float = 15.0,
) -> FastAPI:
    stub = Stub(token, key, store, live_events, live_interval)
    s = stub.store

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(stub.live()) if stub.live_events else None
        try:
            yield
        finally:
            if task:
                task.cancel()

    app = FastAPI(
        title="AnotherNote admin API (stand-in)", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.stub = stub

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            400: "invalid",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "invalid",
            409: "conflict",
        }.get(exc.status_code, "unavailable")
        return error(exc.status_code, code, exc.detail if isinstance(exc.detail, str) else "error")

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = list(first.get("loc", ()))
        if loc and loc[0] in ("body", "query", "path", "header", "cookie"):
            loc = loc[1:]
        where = ".".join(str(p) for p in loc)
        return error(400, "invalid", f"{where}: {first.get('msg', 'not valid')}" if where else "not valid")

    r = APIRouter(prefix="/admin/v1")

    @r.get("/health")
    async def health() -> Any:
        return S.dump(S.Health(ok=True, db=True, redis=True, version=VERSION))

    # --- overview and metrics -------------------------------------------------------
    @r.get("/overview")
    async def overview(request: Request, to: Optional[date] = None) -> Any:
        f, t = day_range(s, _from(request), to)
        now = s.current()
        today = now.date()
        alive = [u for u in s.users.values() if u.status != "deleted"]
        guardians = {link.guardian_id for link in s.links if link.status == "active"}

        def active_on(days: int) -> int:
            return len(
                {uid for (uid, d), sec in s.activity.items() if sec > 0 and today - timedelta(days=days) < d <= today}
            )

        sign_ins_today = [e for e in s.auth_events if e.created_at.date() == today and e.kind == "sign_in"]
        by_method: dict[str, int] = {}
        for e in sign_ins_today:
            by_method[e.method or "unknown"] = by_method.get(e.method or "unknown", 0) + 1
        live = s.live_tokens()
        month_start = today.replace(day=1)
        today_rows = [u for u in s.usage if u.day == today]
        month_rows = [u for u in s.usage if u.day >= month_start]
        features: dict[str, list[UsageDay]] = {}
        for row in month_rows:
            features.setdefault(row.feature, []).append(row)
        top = sorted(
            (
                S.FeatureCost(feature=k, cost_usd=usage_numbers(v)["cost_usd"], tokens=sum(x.tokens for x in v))
                for k, v in features.items()
            ),
            key=lambda fc: (-(fc.cost_usd or 0), -fc.tokens),
        )[:5]
        waiting = [x for x in s.tickets.values() if x.status in ("open", "waiting_on_us")]
        oldest = min((x.last_user_at or x.created_at for x in waiting), default=None)
        result = S.Overview(
            range=rng_model(f, t),
            accounts=S.Accounts(
                total=len(alive),
                adults=sum(1 for u in alive if u.account_kind == "standard"),
                children=sum(1 for u in alive if u.account_kind == "managed_child"),
                teachers=sum(1 for u in alive if u.role == "teacher"),
                guardians=len(guardians),
                deactivated=sum(1 for u in alive if not u.is_active),
            ),
            activity=S.Activity(
                online_now=sum(1 for u in alive if u.last_seen_at and now - u.last_seen_at < timedelta(minutes=5)),
                active_today=active_on(1),
                active_7d=active_on(7),
                active_30d=active_on(30),
            ),
            sign_ins=S.SignInsToday(
                today=len(sign_ins_today),
                failed_today=sum(
                    1 for e in s.auth_events if e.created_at.date() == today and e.kind == "sign_in_failed"
                ),
                by_method_today=by_method,
            ),
            sessions=S.Sessions(live=len(live), users_with_live_sessions=len({x.user_id for x in live})),
            usage=S.OverviewUsage(
                tokens_today=sum(x.tokens for x in today_rows),
                cost_today_usd=usage_numbers(today_rows)["cost_usd"],
                cost_month_usd=usage_numbers(month_rows)["cost_usd"],
                budget_month_usd=BUDGET_MONTH_USD,
                top_features_month=top,
            ),
            tickets=S.OverviewTickets(
                open=sum(1 for x in s.tickets.values() if x.status == "open"),
                waiting_on_us=sum(1 for x in s.tickets.values() if x.status == "waiting_on_us"),
                oldest_open_hours=round((now - oldest).total_seconds() / 3600, 1) if oldest else None,
            ),
            storage=S.Storage(
                pdfs=sum(u.footprint["pdfs"] for u in alive), pdf_bytes=sum(u.footprint["pdf_bytes"] for u in alive)
            ),
            generated_at=now,
        )
        return S.dump(result)

    @r.get("/metrics/active-users")
    async def active_users(request: Request, to: Optional[date] = None, granularity: str = "day") -> Any:
        f, t = day_range(s, _from(request), to)
        per_day: dict[date, set[int]] = {}
        for (uid, d), sec in s.activity.items():
            if sec > 0:
                per_day.setdefault(d, set()).add(uid)
        series = [
            S.DauPoint(day=f + timedelta(days=i), dau=len(per_day.get(f + timedelta(days=i), ())))
            for i in range((t - f).days + 1)
        ]
        window = lambda days: len(set().union(*(per_day.get(t - timedelta(days=i), set()) for i in range(days))))  # noqa: E731
        return S.dump(
            S.ActiveUsers(
                range=rng_model(f, t), granularity="day", series=series, wau=window(7), mau=window(30), as_of=t
            )
        )

    @r.get("/metrics/sign-ins")
    async def sign_ins(request: Request, to: Optional[date] = None, group: str = "method") -> Any:
        f, t = day_range(s, _from(request), to)
        counts: dict[tuple[date, str], int] = {}
        failures: dict[date, int] = {}
        for e in s.auth_events:
            if not in_range(e.created_at, f, t):
                continue
            if e.kind == "sign_in":
                counts[(e.created_at.date(), e.method or "unknown")] = (
                    counts.get((e.created_at.date(), e.method or "unknown"), 0) + 1
                )
            elif e.kind == "sign_in_failed":
                failures[e.created_at.date()] = failures.get(e.created_at.date(), 0) + 1
        series = [S.SignInPoint(day=d, method=m, count=c) for (d, m), c in sorted(counts.items())]
        fails = [
            S.DayCount(day=f + timedelta(days=i), count=failures.get(f + timedelta(days=i), 0))
            for i in range((t - f).days + 1)
        ]
        return S.dump(
            S.SignIns(
                range=rng_model(f, t),
                group="method",
                series=series,
                failures=fails,
                totals=S.SignInTotals(sign_ins=sum(counts.values()), failures=sum(failures.values())),
            )
        )

    @r.get("/metrics/online-now")
    async def online_now() -> Any:
        now = s.current()
        live = s.live_tokens()
        online = sum(
            1
            for u in s.users.values()
            if u.status != "deleted" and u.last_seen_at and now - u.last_seen_at < timedelta(minutes=5)
        )
        return S.dump(
            S.OnlineNow(
                online_now=online,
                live_sessions=len(live),
                users_with_live_sessions=len({x.user_id for x in live}),
                generated_at=now,
            )
        )

    # --- people ------------------------------------------------------------------------
    def get_user(user_id: int) -> User:
        user = s.users.get(user_id)
        if not user:
            raise HTTPException(404, "No such account.")
        return user

    @r.get("/users")
    async def users(
        q: Optional[str] = None,
        kind: Optional[str] = None,
        role: Optional[str] = None,
        plan: Optional[str] = None,
        org: Optional[int] = None,
        active: Optional[str] = None,
        status: Optional[str] = None,
        sort: str = "newest",
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        today = s.current().date()
        rows = list(s.users.values())
        if q:
            q = q.strip()
            if q.isdigit():
                rows = [u for u in rows if u.id == int(q)]
            elif "@" in q:
                # The real API compares HMAC(pepper, lower(email)) with the view's email_lookup.
                rows = [u for u in rows if u.email and u.email.lower() == q.lower()]
            elif len(q) <= 3:
                rows = [u for u in rows if u.username and u.username[:3].lower().startswith(q.lower())]
            else:
                rows = [u for u in rows if u.username and u.username.lower() == q.lower()]
        if kind:
            rows = [u for u in rows if (u.account_kind or "standard") == kind]
        if role:
            rows = [u for u in rows if (u.role or "none") == role]
        if plan:
            rows = [u for u in rows if s.effective_plan(u)[0].id == plan]
        if org:
            rows = [u for u in rows if u.org_id == org]
        if active:
            if active == "never":
                ever = {uid for (uid, _d) in s.activity}
                rows = [u for u in rows if u.id not in ever and not u.last_login]
            else:
                days = {"today": 1, "7d": 7, "30d": 30}[active]
                ids = {
                    uid for (uid, d), sec in s.activity.items() if sec > 0 and today - timedelta(days=days) < d <= today
                }
                rows = [u for u in rows if u.id in ids]
        if status:
            rows = [u for u in rows if u.status == status]
        far = datetime(1970, 1, 1, tzinfo=UTC)
        keys: dict[str, Callable[[User], Any]] = {
            "newest": lambda u: (-u.created_at.timestamp(), -u.id),
            "oldest": lambda u: (u.created_at.timestamp(), u.id),
            "last_seen": lambda u: -(u.last_seen_at or far).timestamp(),
            "last_sign_in": lambda u: -(u.last_login or far).timestamp(),
            "tokens_30d": lambda u: -s.usage_30d(u.id)[0],
            "cost_30d": lambda u: -(s.usage_30d(u.id)[1] or 0),
        }
        rows.sort(key=keys.get(sort, keys["newest"]))
        page, next_cursor = paginate(rows, cursor, limit)
        counts = live_counts(s)
        return S.dump(S.UserList(items=[user_row(s, u, counts) for u in page], next_cursor=next_cursor))

    @r.get("/users/{user_id}")
    async def user_detail(user_id: int) -> Any:
        user = get_user(user_id)
        now = s.current()
        today = now.date()
        tokens_by_feature: dict[str, list[UsageDay]] = {}
        for row in s._usage_by_user().get(user.id, []):
            if row.day > today - timedelta(days=30):
                tokens_by_feature.setdefault(row.feature, []).append(row)
        features = sorted(
            (
                S.FeatureUsage(feature=k, tokens=sum(x.tokens for x in v), cost_usd=usage_numbers(v)["cost_usd"])
                for k, v in tokens_by_feature.items()
            ),
            key=lambda fu: -fu.tokens,
        )
        links = []
        for link in s.links:
            if user.id not in (link.child_id, link.guardian_id):
                continue
            is_child = link.child_id == user.id
            links.append(
                S.FamilyLink(
                    id=link.id,
                    relation="guardian" if is_child else "child",  # what the other account is to this one
                    other_user_id=link.guardian_id if is_child else link.child_id,
                    origin=link.origin,  # type: ignore[arg-type]
                    status=link.status,  # type: ignore[arg-type]
                    activated_at=link.activated_at,
                    revoked_at=link.revoked_at,
                )
            )
        month_ago = now - timedelta(days=30)
        mine = [e for e in s.auth_events if e.user_id == user.id and e.created_at >= month_ago]
        fp = user.footprint
        detail = S.UserDetail(
            user=user_row(s, user, live_counts(s)),
            profile=S.Profile(
                auth_provider=user.auth_provider,
                org_role=user.org_role,
                onboarding_completed=user.onboarding_completed,
                credentials_locked=user.credentials_locked,
                pin_locked_until=user.pin_locked_until,
                xp=user.xp,
                deleted_at=user.deleted_at,
                is_demo=user.is_demo,
                email_domain=user.email.split("@", 1)[1].lower() if user.email else None,
            ),
            footprint=S.Footprint(
                **{
                    k: fp[k]
                    for k in (
                        "study_sessions",
                        "notes",
                        "youtube_sessions",
                        "pdfs",
                        "office_files",
                        "pdf_bytes",
                        "highlights",
                        "sticky_notes",
                        "answers",
                    )
                },
                last_session_at=(user.last_seen_at - timedelta(hours=3)) if user.last_seen_at else None,
            ),
            family=S.Family(
                guardians_active=sum(1 for x in links if x.relation == "guardian" and x.status == "active"),
                guardians_revoked=sum(1 for x in links if x.relation == "guardian" and x.status == "revoked"),
                children_active=sum(1 for x in links if x.relation == "child" and x.status == "active"),
                children_revoked=sum(1 for x in links if x.relation == "child" and x.status == "revoked"),
                links=links,
            ),
            security=S.UserSecurity(
                failed_sign_ins_30d=sum(1 for e in mine if e.kind == "sign_in_failed"),
                locked_until=user.pin_locked_until if user.pin_locked_until and user.pin_locked_until > now else None,
                replays_30d=sum(1 for e in mine if e.kind == "refresh_replay"),
            ),
            usage_by_feature_30d=features,
            activity_30d=[
                S.ActiveDay(
                    day=today - timedelta(days=i),
                    active_seconds=s.activity.get((user.id, today - timedelta(days=i)), 0),
                )
                for i in range(29, -1, -1)
            ],
            note=NOTE,
        )
        return S.dump(detail)

    @r.post("/users/{user_id}/reveal-email")
    async def reveal(request: Request, user_id: int, body: ReasonIn) -> Any:
        need(request, SUPPORT_UP)
        require_reason(body.reason)
        user = get_user(user_id)
        if body.ticket_id:
            note_audit(request, ticket_id=body.ticket_id)
        return S.dump(S.RevealedEmail(email=user.email, first_name=user.first_name))

    @r.get("/users/{user_id}/sessions")
    async def sessions(user_id: int) -> Any:
        get_user(user_id)
        items = [
            S.LiveSession(
                session_id=t.id,
                created_at=t.created_at,
                expires_at=t.expires_at,
                device=S.SessionDevice(**t.device) if t.device else None,
            )
            for t in sorted(s.live_tokens(user_id), key=lambda t: t.created_at, reverse=True)
        ]
        return S.dump(S.SessionList(items=items))

    @r.post("/users/{user_id}/sign-out-everywhere")
    async def sign_out_everywhere(request: Request, user_id: int, body: ReasonIn) -> Any:
        need(request, SUPPORT_UP)
        require_reason(body.reason)
        user = get_user(user_id)
        ended = 0
        for t in s.live_tokens(user.id):
            t.blacklisted = True
            ended += 1
        user.token_epoch += 1
        s.auth_events.append(
            AuthEvent(
                s.next_id("auth"),
                s.current(),
                user.id,
                "admin_action",
                None,
                "sign_out_everywhere",
                None,
                None,
                None,
                None,
            )
        )
        note_audit(request, sessions_ended=ended)
        return S.dump(S.SignOutResult(sessions_ended=ended))

    async def set_active(request: Request, user_id: int, body: ReasonIn, active: bool) -> Any:
        need(request, OWNER)
        require_reason(body.reason)
        user = get_user(user_id)
        if user.deleted_at:
            raise HTTPException(409, "This account is deleted.")
        if user.is_active != active:
            user.is_active = active
            if not active:
                user.token_epoch += 1
            s.auth_events.append(
                AuthEvent(
                    s.next_id("auth"),
                    s.current(),
                    user.id,
                    "admin_action",
                    None,
                    "reactivate" if active else "deactivate",
                    None,
                    None,
                    None,
                    None,
                )
            )
        return S.dump(S.ActiveResult(is_active=user.is_active))

    @r.post("/users/{user_id}/deactivate")
    async def deactivate(request: Request, user_id: int, body: ReasonIn) -> Any:
        return await set_active(request, user_id, body, False)

    @r.post("/users/{user_id}/reactivate")
    async def reactivate(request: Request, user_id: int, body: ReasonIn) -> Any:
        return await set_active(request, user_id, body, True)

    @r.get("/users/{user_id}/usage")
    async def user_usage(request: Request, user_id: int, to: Optional[date] = None, group: str = "day") -> Any:
        get_user(user_id)
        if group not in ("day", "feature", "provider", "model"):
            raise HTTPException(400, "group: not one of day, feature, provider, model")
        f, t = day_range(s, _from(request), to)
        rows = [x for x in s._usage_by_user().get(user_id, []) if f <= x.day <= t]
        return S.dump(summarize(rows, group, f, t))

    @r.get("/users/{user_id}/auth-events")
    async def user_auth_events(request: Request, user_id: int, cursor: Optional[str] = None, limit: int = 50) -> Any:
        need(request, SUPPORT_UP)
        get_user(user_id)
        events = sorted((e for e in s.auth_events if e.user_id == user_id), key=lambda e: e.id, reverse=True)
        page, next_cursor = paginate(events, cursor, limit)
        return S.dump(S.AuthEventList(items=[auth_model(e) for e in page], next_cursor=next_cursor))

    @r.get("/users/{user_id}/tickets")
    async def user_tickets(request: Request, user_id: int, cursor: Optional[str] = None, limit: int = 50) -> Any:
        need(request, SUPPORT_UP)
        get_user(user_id)
        mine = sorted((t for t in s.tickets.values() if t.user_id == user_id), key=lambda t: t.created_at, reverse=True)
        page, next_cursor = paginate(mine, cursor, limit)
        return S.dump(
            S.TicketList(items=[ticket_row(s, t) for t in page], next_cursor=next_cursor, counts=ticket_counts(mine))
        )

    def subject_plan(subject_type: str, subject_id: int, user: Optional[User] = None) -> S.SubjectPlan:
        if user is not None:
            plan, source, a = s.effective_plan(user)
        else:
            a = s.current_assignment(subject_type, subject_id)
            plan, source = (s.plans[a.plan_id], "organization") if a else (s.default_plan(), "default")
        history = [
            assignment_model(x)
            for x in reversed(s.assignments)
            if x.subject_type == subject_type and x.subject_id == subject_id
        ]
        return S.SubjectPlan(
            effective=S.EffectivePlan(
                plan=S.PlanName(id=plan.id, name=plan.name),
                source=source,
                status=a.status if a else "active",  # type: ignore[arg-type]
                assignment_id=a.id if a else None,
                starts_at=a.starts_at if a else None,
                ends_at=a.ends_at if a else None,
            ),
            history=history,
        )

    @r.get("/users/{user_id}/plan")
    async def user_plan(user_id: int) -> Any:
        user = get_user(user_id)
        return S.dump(subject_plan("user", user.id, user))

    def assign(request: Request, subject_type: str, subject_id: int, body: AssignIn) -> Any:
        actor = need(request, OWNER)
        if len(body.note.strip()) < 3:
            raise HTTPException(400, "note: a note is required")
        plan = s.plans.get(body.plan_id)
        if not plan:
            raise HTTPException(400, "plan_id: no such plan")
        if body.status not in ("active", "trial", "canceled"):
            raise HTTPException(400, "status: must be active, trial or canceled")
        now = s.current()
        current = s.current_assignment(subject_type, subject_id)
        note_audit(request, plan_id=body.plan_id, status=body.status)
        if body.status == "canceled":
            if not current:
                raise HTTPException(409, "There is no plan assignment to cancel.")
            current.status, current.ends_at = "canceled", now
            return S.dump(assignment_model(current))
        if not plan.is_active:
            raise HTTPException(409, "That plan is not active.")
        if current:
            current.status, current.ends_at = "canceled", now
        new = Assignment(
            s.next_id("assignment"),
            subject_type,
            subject_id,
            plan.id,
            body.status,
            "manual",
            now,
            body.ends_at,
            body.note.strip(),
            actor.email,
            now,
        )
        s.assignments.append(new)
        return S.dump(assignment_model(new))

    @r.put("/users/{user_id}/plan")
    async def put_user_plan(request: Request, user_id: int, body: AssignIn) -> Any:
        need(request, OWNER)
        get_user(user_id)
        return assign(request, "user", user_id, body)

    # --- usage -------------------------------------------------------------------------
    @r.get("/usage/summary")
    async def usage_summary(request: Request, to: Optional[date] = None, group: str = "feature") -> Any:
        if group not in ("day", "feature", "provider", "model"):
            raise HTTPException(400, "group: not one of day, feature, provider, model")
        f, t = day_range(s, _from(request), to)
        result = summarize([x for x in s.usage if f <= x.day <= t], group, f, t)
        today = s.current().date()
        month_rows = [x for x in s.usage if x.day >= today.replace(day=1)]
        result.month_to_date = S.MonthToDate(
            month=today.strftime("%Y-%m"), cost_usd=usage_numbers(month_rows)["cost_usd"], budget_usd=BUDGET_MONTH_USD
        )
        return S.dump(result)

    @r.get("/usage/top-users")
    async def top_users(request: Request, to: Optional[date] = None, metric: str = "cost", limit: int = 20) -> Any:
        if metric not in ("cost", "tokens", "characters"):
            raise HTTPException(400, "metric: not one of cost, tokens, characters")
        f, t = day_range(s, _from(request), to)
        per_user: dict[int, list[UsageDay]] = {}
        for x in s.usage:
            if x.user_id is not None and f <= x.day <= t:
                per_user.setdefault(x.user_id, []).append(x)
        items = []
        for uid, rows in per_user.items():
            n = usage_numbers(rows)
            tokens = n["input_tokens"] + n["output_tokens"]
            value = {"cost": n["cost_usd"] or 0.0, "tokens": tokens, "characters": n["characters"]}[metric]
            items.append(
                S.TopUser(
                    user=user_ref(s.users[uid]),
                    value=value,
                    calls=n["calls"],
                    tokens=tokens,
                    characters=n["characters"],
                    cost_usd=n["cost_usd"],
                )
            )
        items.sort(key=lambda x: -x.value)
        return S.dump(S.TopUsers(range=rng_model(f, t), metric=metric, items=items[: max(1, min(100, limit))]))  # type: ignore[arg-type]

    @r.get("/usage/anomalies")
    async def anomalies(request: Request) -> Any:
        raw = request.query_params.get("date")
        try:
            day = date.fromisoformat(raw) if raw else s.current().date() - timedelta(days=1)
        except ValueError:
            raise HTTPException(400, "date: not a date") from None
        items = []
        for uid in {x.user_id for x in s.usage if x.day == day and x.user_id is not None}:
            value = s.daily_tokens(uid, day)
            median = s.median_daily_tokens(uid, day)
            if value >= 20_000 and median > 0 and value > 5 * median:
                user = s.users[uid]
                items.append(
                    S.Anomaly(
                        user=user_ref(user),
                        metric="tokens",
                        value=value,
                        median_30d=median,
                        ratio=round(value / median, 1),
                        reason="spike",
                        plan_id=s.effective_plan(user)[0].id,
                    )
                )
        items.sort(key=lambda a: -(a.ratio or 0))
        return S.dump(S.Anomalies(date=day, items=items))

    @r.get("/usage/prices")
    async def prices(request: Request) -> Any:
        need(request, OWNER)
        items = [S.Price(provider=p, model=m, **v) for (p, m), v in PRICES.items()]
        return S.dump(
            S.Prices(items=items, source="devstub example values, not real prices", budget_month_usd=BUDGET_MONTH_USD)
        )

    # --- plans -------------------------------------------------------------------------
    def plan_model(p: Plan) -> S.Plan:
        current = [
            a
            for a in s.assignments
            if a.plan_id == p.id and a.status in ("active", "trial") and (a.ends_at is None or a.ends_at > s.current())
        ]
        return S.Plan(
            id=p.id,
            name=p.name,
            description=p.description,
            is_default=p.is_default,
            is_active=p.is_active,
            limits=S.PlanLimits(**p.limits),
            price_cents=p.price_cents,
            currency=p.currency,
            interval=p.interval,  # type: ignore[arg-type]
            created_at=p.created_at,
            updated_at=p.updated_at,
            assignments=S.AssignmentCounts(
                active=sum(1 for a in current if a.status == "active"),
                trial=sum(1 for a in current if a.status == "trial"),
            ),
        )

    @r.get("/plans")
    async def plans() -> Any:
        return S.dump(S.PlanList(items=[plan_model(p) for p in s.plans.values()]))

    @r.post("/plans")
    async def create_plan(request: Request, body: PlanIn) -> Any:
        need(request, OWNER)
        if not body.id or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", body.id) or not body.name:
            raise HTTPException(400, "id and name are required")
        if body.id in s.plans:
            raise HTTPException(409, "A plan with that id exists.")
        now = s.current()
        plan = Plan(
            body.id,
            body.name,
            body.description or "",
            False,
            True if body.is_active is None else body.is_active,
            (body.limits or S.PlanLimits()).model_dump(exclude_none=True),
            body.price_cents,
            body.currency,
            body.interval,
            now,
            now,
        )
        s.plans[plan.id] = plan
        note_audit(request, plan_id=plan.id)
        if body.is_default:
            for other in s.plans.values():
                other.is_default = other.id == plan.id
        return S.dump(plan_model(plan))

    @r.patch("/plans/{plan_id}")
    async def update_plan(request: Request, plan_id: str, body: PlanIn) -> Any:
        need(request, OWNER)
        plan = s.plans.get(plan_id)
        if not plan:
            raise HTTPException(404, "No such plan.")
        changes = body.model_dump(exclude_unset=True)
        if "id" in changes:
            raise HTTPException(400, "id: cannot be changed")
        if changes.get("is_default") is False and plan.is_default:
            raise HTTPException(409, "Exactly one plan is the default: make another plan the default instead.")
        if changes.get("is_active") is False and plan.is_default:
            raise HTTPException(409, "The default plan cannot be turned off.")
        for field_name in ("name", "description", "is_active", "price_cents", "currency", "interval"):
            if field_name in changes:
                setattr(plan, field_name, changes[field_name])
        if "limits" in changes:
            plan.limits = (body.limits or S.PlanLimits()).model_dump(exclude_none=True)
        if changes.get("is_default"):
            for other in s.plans.values():
                other.is_default = other.id == plan.id
        plan.updated_at = s.current()
        note_audit(request, fields=sorted(changes))
        return S.dump(plan_model(plan))

    # --- organisations ---------------------------------------------------------------
    def org_row(oid: int) -> S.OrgRow:
        o = s.orgs[oid]
        a = s.current_assignment("organization", oid)
        plan = (
            S.PlanRef(id=a.plan_id, name=s.plans[a.plan_id].name, source="organization", status=a.status)
            if a
            else S.PlanRef(id=s.default_plan().id, name=s.default_plan().name, source="default", status="active")
        )
        members = sum(1 for u in s.users.values() if u.org_id == oid and u.status != "deleted")
        return S.OrgRow(
            id=o.id,
            name=o.name,
            slug=o.slug,
            sso_provider=o.sso_provider,
            sso_enforced=o.sso_enforced,
            created_at=o.created_at,
            members=members,
            plan=plan,
        )

    @r.get("/orgs")
    async def orgs(q: Optional[str] = None, cursor: Optional[str] = None, limit: int = 50) -> Any:
        found = list(s.orgs.values())
        if q:
            needle = q.strip().lower()
            found = [
                o
                for o in found
                if needle in o.name.lower() or needle in o.slug or any(needle in d for d, _ in o.domains)
            ]
        found.sort(key=lambda o: o.name.lower())
        page, next_cursor = paginate(found, cursor, limit)
        return S.dump(S.OrgList(items=[org_row(o.id) for o in page], next_cursor=next_cursor))

    @r.get("/orgs/{org_id}")
    async def org_detail(org_id: int) -> Any:
        o = s.orgs.get(org_id)
        if not o:
            raise HTTPException(404, "No such organisation.")
        members = [u for u in s.users.values() if u.org_id == org_id and u.status != "deleted"]
        return S.dump(
            S.OrgDetail(
                org=org_row(org_id),
                domains=[S.OrgDomain(domain=d, verified=v) for d, v in o.domains],
                member_counts=S.OrgMemberCounts(
                    total=len(members),
                    teachers=sum(1 for u in members if u.role == "teacher"),
                    students=sum(1 for u in members if u.role == "student"),
                    org_owners=sum(1 for u in members if u.org_role == "owner"),
                    org_admins=sum(1 for u in members if u.org_role == "admin"),
                ),
                plan=subject_plan("organization", org_id),
            )
        )

    @r.put("/orgs/{org_id}/plan")
    async def put_org_plan(request: Request, org_id: int, body: AssignIn) -> Any:
        need(request, OWNER)
        if org_id not in s.orgs:
            raise HTTPException(404, "No such organisation.")
        return assign(request, "organization", org_id, body)

    # --- tickets ------------------------------------------------------------------------
    def ticket_counts(tickets: Iterable[Ticket]) -> S.TicketCounts:
        counts = {k: 0 for k in ("open", "waiting_on_us", "waiting_on_user", "resolved", "closed")}
        for t in tickets:
            counts[t.status] += 1
        return S.TicketCounts(**counts)

    def get_ticket(ticket_id: int) -> Ticket:
        t = s.tickets.get(ticket_id)
        if not t:
            raise HTTPException(404, "No such ticket.")
        return t

    @r.get("/tickets")
    async def tickets(
        request: Request,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        q: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        need(request, TICKET_READERS)
        found = list(s.tickets.values())
        if reason:
            found = [t for t in found if t.reason == reason]
        if priority:
            found = [t for t in found if t.priority == priority]
        if assignee:
            found = [
                t
                for t in found
                if (t.assignee_email is None if assignee == "none" else t.assignee_email == assignee.lower())
            ]
        if q:
            needle = q.strip().lower()
            number = re.fullmatch(r"(an-)?0*(\d+)", needle)
            found = [
                t
                for t in found
                if (number and t.id == int(number.group(2)))
                or needle in t.subject.lower()
                or needle in t.messages[0].body.lower()
            ]
        counts = ticket_counts(found)
        if status:
            found = [t for t in found if t.status == status]
        if status in ("open", "waiting_on_us"):
            found.sort(key=lambda t: t.last_user_at or t.created_at)
        else:
            found.sort(key=lambda t: t.updated_at, reverse=True)
        page, next_cursor = paginate(found, cursor, limit)
        return S.dump(S.TicketList(items=[ticket_row(s, t) for t in page], next_cursor=next_cursor, counts=counts))

    @r.get("/tickets/{ticket_id}")
    async def ticket(request: Request, ticket_id: int) -> Any:
        need(request, TICKET_READERS)
        t = get_ticket(ticket_id)
        user = s.users[t.user_id]
        tokens, cost = s.usage_30d(user.id)
        org = s.org_of(user)
        return S.dump(
            S.TicketDetail(
                ticket=ticket_row(s, t),
                page_url=t.page_url,
                context=S.TicketContext(**t.context) if t.context else None,
                closed_at=t.closed_at,
                messages=[
                    S.TicketMessage(
                        id=m.id,
                        author=m.author,
                        staff_email=m.staff_email,
                        body=m.body,
                        internal=m.internal,
                        created_at=m.created_at,
                    )
                    for m in t.messages
                ],  # type: ignore[arg-type]
                user=S.TicketUser(
                    id=user.id,
                    identity=identity(user),
                    kind=user.account_kind or "standard",
                    organization=S.OrgRef(id=org.id, name=org.name) if org else None,  # type: ignore[arg-type]
                    plan=plan_ref(s, user),
                    last_seen_at=user.last_seen_at,
                    usage_30d=S.Usage30d(tokens=tokens, cost_usd=cost),
                ),
            )
        )

    @r.post("/tickets/{ticket_id}/messages")
    async def add_message(request: Request, ticket_id: int, body: MessageIn) -> Any:
        actor = need(request, SUPPORT_UP)
        t = get_ticket(ticket_id)
        text = body.body.strip()
        if not text or len(text) > 10_000:
            raise HTTPException(400, "body: must be 1 to 10,000 characters")
        now = s.current()
        message = Message(s.next_id("message"), "staff", actor.email, text, body.internal, now)
        t.messages.append(message)
        t.updated_at = now
        if not body.internal:
            t.status, t.last_staff_at, t.closed_at = "waiting_on_user", now, None
            if not t.assignee_email:
                t.assignee_email = actor.email
        else:
            request.scope["state"]["audit"]["action"] = "ticket.note"
        return S.dump(
            S.TicketMessage(
                id=message.id,
                author="staff",
                staff_email=actor.email,
                body=text,
                internal=body.internal,
                created_at=now,
            )
        )

    @r.patch("/tickets/{ticket_id}")
    async def update_ticket(request: Request, ticket_id: int, body: TicketPatchIn) -> Any:
        need(request, SUPPORT_UP)
        t = get_ticket(ticket_id)
        changes = body.model_dump(exclude_unset=True)
        if "status" in changes:
            if body.status not in ("open", "waiting_on_us", "waiting_on_user", "resolved", "closed"):
                raise HTTPException(400, "status: not a ticket status")
            t.status = body.status
            t.closed_at = s.current() if body.status in ("resolved", "closed") else None
        if "priority" in changes:
            if body.priority not in ("low", "normal", "high", "urgent"):
                raise HTTPException(400, "priority: not a priority")
            t.priority = body.priority
        if "assignee_email" in changes:
            t.assignee_email = body.assignee_email.lower() if body.assignee_email else None
        if "tags" in changes:
            t.tags = list(dict.fromkeys(body.tags or []))[:10]
        t.updated_at = s.current()
        note_audit(request, fields=sorted(changes))
        return S.dump(ticket_row(s, t))

    # --- live events ------------------------------------------------------------------
    def event_model(e: Outbox) -> S.OutboxEvent:
        return S.OutboxEvent(id=e.id, kind=e.kind, ticket_id=e.ticket_id, created_at=e.created_at)  # type: ignore[arg-type]

    @r.get("/events")
    async def events(request: Request, after: Optional[int] = None, limit: int = 100) -> Any:
        need(request, SUPPORT_UP)
        limit = max(1, min(100, limit))
        found = [e for e in s.outbox if after is None or e.id > after]
        found = found[:limit] if after is not None else found[-limit:]
        return S.dump(S.EventList(items=[event_model(e) for e in found]))

    @r.get("/events/stream")
    async def event_stream(request: Request, after: Optional[int] = None) -> StreamingResponse:
        need(request, SUPPORT_UP)
        queue: asyncio.Queue[Outbox] = asyncio.Queue()
        stub.subscribers.add(queue)
        backlog = [e for e in s.outbox if after is not None and e.id > after][-100:]

        def frame(e: Outbox) -> bytes:
            return f"id: {e.id}\nevent: {e.kind}\ndata: {json.dumps(S.dump(event_model(e)))}\n\n".encode()

        async def gen() -> AsyncIterator[bytes]:
            try:
                for e in backlog:
                    yield frame(e)
                while True:
                    try:
                        e = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                        yield frame(e)
                    except TimeoutError:
                        yield b": ping\n\n"
            finally:
                stub.subscribers.discard(queue)

        return StreamingResponse(gen(), media_type="text/event-stream")

    # --- security -------------------------------------------------------------------------
    @r.get("/security/summary")
    async def security_summary(request: Request, to: Optional[date] = None) -> Any:
        need(request, SUPPORT_UP)
        f, t = day_range(s, _from(request), to, default_days=7)
        events = [e for e in s.auth_events if in_range(e.created_at, f, t)]
        failed = [e for e in events if e.kind == "sign_in_failed"]
        per_hour: dict[datetime, int] = {}
        for e in failed:
            hour = e.created_at.replace(minute=0, second=0, microsecond=0)
            per_hour[hour] = per_hour.get(hour, 0) + 1
        start = datetime(f.year, f.month, f.day, tzinfo=UTC)
        end = min(datetime(t.year, t.month, t.day, 23, tzinfo=UTC), s.current().replace(minute=0, second=0))
        hours = []
        h = start
        while h <= end:
            hours.append(S.HourCount(hour=h, count=per_hour.get(h, 0)))
            h += timedelta(hours=1)
        reasons: dict[str, int] = {}
        for e in failed:
            reasons[e.reason or "unknown"] = reasons.get(e.reason or "unknown", 0) + 1
        networks: dict[str, list[AuthEvent]] = {}
        for e in failed:
            if e.ip_prefix_hash:
                networks.setdefault(e.ip_prefix_hash, []).append(e)
        top = sorted(networks.items(), key=lambda kv: -len(kv[1]))[:10]
        return S.dump(
            S.SecuritySummary(
                range=rng_model(f, t),
                totals=S.SecurityTotals(
                    sign_ins=sum(1 for e in events if e.kind == "sign_in"),
                    failed=len(failed),
                    lockouts=sum(1 for e in events if e.kind == "pin_locked"),
                    replays=sum(1 for e in events if e.kind == "refresh_replay"),
                    pin_resets=sum(1 for e in events if e.kind == "pin_reset"),
                    sign_outs_everywhere=sum(
                        1
                        for e in events
                        if e.kind == "sign_out_everywhere"
                        or (e.kind == "admin_action" and e.reason == "sign_out_everywhere")
                    ),
                ),
                failed_per_hour=hours,
                failures_by_reason=[
                    S.ReasonCount(reason=k, count=v) for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])
                ],
                top_networks=[
                    S.Network(
                        ip_prefix_hash=k,
                        failures=len(v),
                        identifiers=len({e.identifier_hash for e in v if e.identifier_hash}),
                        countries=sorted({e.country for e in v if e.country}),
                        last_at=max(e.created_at for e in v),
                    )
                    for k, v in top
                ],
            )
        )

    @r.get("/security/auth-events")
    async def security_events(
        request: Request,
        kind: Optional[str] = None,
        to: Optional[date] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        need(request, SUPPORT_UP)
        f, t = day_range(s, _from(request), to)
        found = [e for e in s.auth_events if in_range(e.created_at, f, t) and (kind is None or e.kind == kind)]
        found.sort(key=lambda e: e.id, reverse=True)
        page, next_cursor = paginate(found, cursor, limit)
        return S.dump(S.AuthEventList(items=[auth_model(e) for e in page], next_cursor=next_cursor))

    # --- analytics: what people did, and what went wrong ---------------------------------
    UTM = ("utm_source", "utm_medium", "utm_campaign")

    def template(path: Optional[str]) -> str:
        return re.sub(
            r"/-?\d+(?=/|$)",
            "/:n",
            re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ":id", path or ""),
        )

    def analytics_model(e: Event) -> S.AnalyticsEvent:
        tags = e.tags or {}
        return S.AnalyticsEvent(
            id=e.id,
            created_at=e.created_at,
            user_id=e.user_id,
            kind=e.kind,
            name=e.name[:160],
            path=e.path,  # type: ignore[arg-type]
            utm_source=tags.get("utm_source"),
            utm_medium=tags.get("utm_medium"),
            utm_campaign=tags.get("utm_campaign"),
        )

    def events_in(f: date, t: date) -> list[Event]:
        return [e for e in s.events if f <= e.created_at.date() <= t]

    @r.get("/analytics/summary")
    async def analytics_summary(request: Request, to: Optional[date] = None) -> Any:
        f, t = day_range(s, _from(request), to)
        found = events_in(f, t)
        per_day = {f + timedelta(days=i): {"view": 0, "action": 0, "error": 0} for i in range((t - f).days + 1)}
        names: dict[tuple[str, str], list[Event]] = {}
        campaigns: dict[tuple[Optional[str], ...], list[Event]] = {}
        for e in found:
            per_day[e.created_at.date()][e.kind] += 1
            names.setdefault((e.kind, e.name), []).append(e)
            tags = e.tags or {}
            if any(tags.get(k) for k in UTM):
                campaigns.setdefault(tuple(tags.get(k) for k in UTM), []).append(e)

        def top(kind: str) -> list[S.NameCount]:
            rows = [
                S.NameCount(name=n, count=len(v), users=len({e.user_id for e in v if e.user_id}))
                for (k, n), v in names.items()
                if k == kind
            ]
            return sorted(rows, key=lambda x: -x.count)[:10]

        return S.dump(
            S.AnalyticsSummary(
                range=rng_model(f, t),
                totals=S.AnalyticsTotals(
                    views=sum(1 for e in found if e.kind == "view"),
                    actions=sum(1 for e in found if e.kind == "action"),
                    errors=sum(1 for e in found if e.kind == "error"),
                    users=len({e.user_id for e in found if e.user_id}),
                ),
                by_day=[S.AnalyticsDay(day=d, **c) for d, c in sorted(per_day.items())],
                top_pages=top("view"),
                top_actions=top("action"),
                campaigns=sorted(
                    (
                        S.Campaign(
                            utm_source=k[0],
                            utm_medium=k[1],
                            utm_campaign=k[2],
                            events=len(v),
                            users=len({e.user_id for e in v if e.user_id}),
                        )
                        for k, v in campaigns.items()
                    ),
                    key=lambda c: -c.events,
                )[:10],
            )
        )

    @r.get("/analytics/errors")
    async def analytics_errors(
        request: Request,
        to: Optional[date] = None,
        q: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        f, t = day_range(s, _from(request), to)
        groups: dict[str, list[Event]] = {}
        for e in events_in(f, t):
            if e.kind == "error" and (not q or q.strip().lower() in e.name.lower()):
                groups.setdefault(e.name, []).append(e)
        items = []
        for name, found in groups.items():
            paths: list[str] = []
            for e in found:
                p = template(e.path)
                if p and p not in paths and len(paths) < 5:
                    paths.append(p)
            days: dict[date, int] = {}
            for e in found:
                days[e.created_at.date()] = days.get(e.created_at.date(), 0) + 1
            items.append(
                S.ErrorGroup(
                    name=name,
                    count=len(found),
                    users=len({e.user_id for e in found if e.user_id}),
                    first_at=min(e.created_at for e in found),
                    last_at=max(e.created_at for e in found),
                    paths=paths,
                    by_day=[S.DayCount(day=d, count=c) for d, c in sorted(days.items())],
                )
            )
        items.sort(key=lambda g: (g.last_at, g.count), reverse=True)
        page, next_cursor = paginate(items, cursor, limit)
        return S.dump(S.ErrorGroups(range=rng_model(f, t), items=page, next_cursor=next_cursor))

    @r.get("/analytics/events")
    async def analytics_events(
        request: Request,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        path: Optional[str] = None,
        user_id: Optional[int] = None,
        to: Optional[date] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        need(request, SUPPORT_UP)
        f, t = day_range(s, _from(request), to)
        if user_id:
            request.scope["state"]["audit"]["target"] = ("user", str(user_id))
        found = [
            e
            for e in events_in(f, t)
            if (not kind or e.kind == kind)
            and (not name or e.name == name)
            and (not path or (e.path or "").startswith(path) or template(e.path).startswith(path))
            and (not user_id or e.user_id == user_id)
        ]
        found.sort(key=lambda e: e.id, reverse=True)
        page, next_cursor = paginate(found, cursor, limit)
        return S.dump(S.AnalyticsEventList(items=[analytics_model(e) for e in page], next_cursor=next_cursor))

    # --- audit --------------------------------------------------------------------------
    @r.get("/audit")
    async def audit(
        request: Request,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        to: Optional[date] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> Any:
        need(request, OWNER)
        f, t = day_range(s, _from(request), to, default_days=365)
        found = [
            a
            for a in s.audit
            if in_range(a.at, f, t)
            and (not actor or a.actor_email == actor.lower())
            and (not action or a.action == action)
        ]
        found.sort(key=lambda a: a.id, reverse=True)
        page, next_cursor = paginate(found, cursor, limit)
        return S.dump(
            S.AuditList(
                items=[
                    S.AuditRow(
                        id=a.id,
                        at=a.at,
                        actor_email=a.actor_email,
                        actor_role=a.actor_role,
                        action=a.action,
                        target_type=a.target_type,
                        target_id=a.target_id,
                        reason=a.reason,
                        request_id=a.request_id,
                        details=a.details,
                    )
                    for a in page
                ],
                next_cursor=next_cursor,
            )
        )

    app.include_router(r)
    app.add_middleware(Gate, stub=stub)
    return app


def _from(request: Request) -> Optional[date]:
    raw = request.query_params.get("from")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(400, "from: not a date") from None


def __getattr__(name: str) -> Any:
    # `devstub.app:app` for uvicorn, built on first access from the environment.
    if name == "app":
        token, key = os.environ.get("ADMIN_SERVICE_TOKEN"), os.environ.get("ADMIN_SIGNING_KEY")
        if not token or not key:
            raise RuntimeError("set ADMIN_SERVICE_TOKEN and ADMIN_SIGNING_KEY (the same values the BFF uses)")
        application = create_stub(
            token,
            key,
            live_events=os.environ.get("STUB_LIVE_EVENTS", "1") == "1",
            live_interval=float(os.environ.get("STUB_LIVE_INTERVAL", "45")),
        )
        globals()["app"] = application
        return application
    raise AttributeError(name)
