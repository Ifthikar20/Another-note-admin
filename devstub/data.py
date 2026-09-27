"""
Made-up data for the stand-in admin API: people, organisations, sign-ins, sessions,
usage, plans, tickets and an audit trail.

Deterministic (one random seed) and anchored to the moment the stub starts, so "online
now", "today" and "this month" look alive. Every name, address and message is invented;
the email domains are reserved ones (example.com, *.test) that belong to nobody.
"""

from __future__ import annotations

import hashlib
import random
import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Optional

UTC = UTC

REASONS: list[tuple[str, str]] = [
    ("sign_in", "I can't sign in, or my account is locked"),
    ("upload", "An upload failed, or a file won't open"),
    ("notes", "The notes, quiz or flashcards look wrong"),
    ("teach", "Teach mode: no voice, the wrong voice, or the mic doesn't work"),
    ("pictures", "A board picture or diagram is wrong or missing"),
    ("slow", "Something is slow, stuck, or won't load"),
    ("family", "Family, parents and child accounts"),
    ("study_tools", "Highlights, sticky notes or study plans"),
    ("account", "My account, organisation or billing"),
    ("idea", "I have an idea or a suggestion"),
    ("other", "Something else"),
]
REASON_LABELS = dict(REASONS)

STAFF = [
    ("leo@anothernote.app", "owner"),
    ("maya@anothernote.app", "support"),
    ("ines@anothernote.app", "support"),
    ("tom@anothernote.app", "analyst"),
]

FIRST = [
    "Sam",
    "Ava",
    "Noah",
    "Maya",
    "Leo",
    "Zara",
    "Omar",
    "Isla",
    "Ethan",
    "Priya",
    "Kofi",
    "Lena",
    "Mateo",
    "Aisha",
    "Finn",
    "Chloe",
    "Ravi",
    "Sofia",
    "Jonah",
    "Amara",
    "Theo",
    "Hana",
    "Luca",
    "Nia",
    "Owen",
    "Ines",
    "Kai",
    "Elif",
    "Max",
    "Yara",
    "Dev",
    "Ruby",
    "Arjun",
    "Mila",
    "Tariq",
    "Grace",
    "Jin",
    "Lucy",
    "Emeka",
    "Freya",
]
LAST = [
    "Okafor",
    "Patel",
    "Kim",
    "Nguyen",
    "Garcia",
    "Smith",
    "Rossi",
    "Haddad",
    "Novak",
    "Silva",
    "Brown",
    "Khan",
    "Murphy",
    "Dubois",
    "Tanaka",
    "Mensah",
    "Costa",
    "Walsh",
    "Singh",
    "Larsen",
]
PERSONAL_DOMAINS = ["example.com", "example.net", "example.org"]
UA = [
    "Chrome · Windows",
    "Chrome · macOS",
    "Safari · macOS",
    "Safari · iOS",
    "Chrome · Android",
    "Edge · Windows",
    "Firefox · Windows",
    "Chrome · ChromeOS",
    "AnotherNote · macOS",
]
UA_WEIGHTS = [26, 12, 10, 14, 10, 8, 4, 12, 4]
COUNTRIES = ["GB", "US", "IE", "CA", "AU", "IN", "DE", "NG", "ZA"]
COUNTRY_WEIGHTS = [38, 30, 6, 6, 5, 6, 4, 3, 2]

ORGS = [
    ("Lincoln High", "lincoln-high", "google", True, [("lincoln.test", True)]),
    ("Riverside Academy", "riverside", "microsoft", False, [("riverside.test", True), ("riverside-staff.test", False)]),
    ("Northgate School District", "northgate", "saml", True, [("northgate.test", True)]),
    ("Maple Tutors", "maple-tutors", None, False, [("mapletutors.test", True)]),
    ("St Anne's College", "st-annes", "google", False, [("stannes.test", True)]),
]

# (feature, weight, providers [(provider, model, share)], per-call units)
CHAT_DS = ("deepseek", "deepseek-chat")
OPUS = ("anthropic", "claude-opus-5")
SONNET = ("anthropic", "claude-sonnet-5")
FEATURES: list[tuple[str, float, list[tuple[tuple[str, str], float]], dict[str, tuple[int, int]]]] = [
    (
        "teach.script",
        0.50,
        [(CHAT_DS, 0.8), (OPUS, 0.2)],
        {"input": (6000, 12000), "output": (1500, 4000), "calls": (1, 6)},
    ),
    ("teach.ask", 0.35, [(CHAT_DS, 0.8), (OPUS, 0.2)], {"input": (3000, 8000), "output": (200, 900), "calls": (1, 8)}),
    (
        "teach.facts",
        0.20,
        [(CHAT_DS, 0.8), (OPUS, 0.2)],
        {"input": (1500, 3000), "output": (200, 500), "calls": (1, 3)},
    ),
    (
        "teach.image_plan",
        0.20,
        [(CHAT_DS, 0.8), (OPUS, 0.2)],
        {"input": (2000, 5000), "output": (150, 400), "calls": (1, 4)},
    ),
    ("note_check", 0.10, [(CHAT_DS, 0.8), (OPUS, 0.2)], {"input": (2500, 6000), "output": (300, 900), "calls": (1, 3)}),
    (
        "pictures.web_search",
        0.15,
        [(("perplexity", "sonar"), 1.0)],
        {"input": (80, 200), "output": (300, 800), "calls": (1, 6)},
    ),
    ("tts", 0.50, [(("speechify", "simba-3.0"), 1.0)], {"characters": (400, 1800), "calls": (5, 40)}),
    ("transcribe.question", 0.10, [(("whisper", "base"), 1.0)], {"audio_ms": (4000, 45000), "calls": (1, 6)}),
    ("pictures.check", 0.15, [(SONNET, 1.0)], {"input": (1500, 3500), "output": (60, 200), "calls": (1, 8)}),
    ("pictures.parts", 0.08, [(SONNET, 1.0)], {"input": (2500, 5000), "output": (200, 600), "calls": (1, 4)}),
    (
        "session.create",
        0.15,
        [(OPUS, 0.5), (CHAT_DS, 0.5)],
        {"input": (8000, 30000), "output": (3000, 9000), "calls": (1, 2)},
    ),
    (
        "questions.more",
        0.10,
        [(CHAT_DS, 0.7), (SONNET, 0.3)],
        {"input": (3000, 7000), "output": (1000, 3000), "calls": (1, 3)},
    ),
    (
        "notes.generate",
        0.30,
        [(CHAT_DS, 0.75), (SONNET, 0.25)],
        {"input": (4000, 12000), "output": (1500, 5000), "calls": (1, 5)},
    ),
    (
        "notes.revise",
        0.08,
        [(CHAT_DS, 0.75), (SONNET, 0.25)],
        {"input": (3000, 9000), "output": (800, 3000), "calls": (1, 3)},
    ),
    (
        "quiz.hint",
        0.20,
        [(CHAT_DS, 0.75), (SONNET, 0.25)],
        {"input": (800, 2000), "output": (60, 200), "calls": (1, 10)},
    ),
    (
        "quiz.section",
        0.20,
        [(CHAT_DS, 0.75), (SONNET, 0.25)],
        {"input": (2500, 6000), "output": (900, 2500), "calls": (1, 4)},
    ),
    (
        "flashcards.section",
        0.15,
        [(CHAT_DS, 0.75), (SONNET, 0.25)],
        {"input": (2500, 6000), "output": (700, 2000), "calls": (1, 4)},
    ),
    ("questions.generate", 0.05, [(CHAT_DS, 1.0)], {"input": (3000, 8000), "output": (1500, 4000), "calls": (1, 2)}),
    ("transcribe.youtube", 0.04, [(("whisper", "base"), 1.0)], {"audio_ms": (300000, 1800000), "calls": (1, 1)}),
]

# Example prices for the stub only, in USD: NOT the providers' prices. The real table is
# app/core/usage_prices.py in playstudy-backend, left empty until the owner fills it in.
# Perplexity is left unknown on purpose, so the "price not set" path shows.
PRICES: dict[tuple[str, str], dict[str, Optional[float]]] = {
    CHAT_DS: {
        "input_per_mtok": 0.30,
        "output_per_mtok": 1.20,
        "cache_read_per_mtok": 0.10,
        "cache_write_per_mtok": None,
        "per_mchar": None,
        "per_request": None,
    },
    OPUS: {
        "input_per_mtok": 15.0,
        "output_per_mtok": 75.0,
        "cache_read_per_mtok": 1.50,
        "cache_write_per_mtok": 18.75,
        "per_mchar": None,
        "per_request": None,
    },
    SONNET: {
        "input_per_mtok": 3.0,
        "output_per_mtok": 15.0,
        "cache_read_per_mtok": 0.30,
        "cache_write_per_mtok": 3.75,
        "per_mchar": None,
        "per_request": None,
    },
    ("speechify", "simba-3.0"): {
        "input_per_mtok": None,
        "output_per_mtok": None,
        "cache_read_per_mtok": None,
        "cache_write_per_mtok": None,
        "per_mchar": 10.0,
        "per_request": None,
    },
    ("perplexity", "sonar"): {
        "input_per_mtok": None,
        "output_per_mtok": None,
        "cache_read_per_mtok": None,
        "cache_write_per_mtok": None,
        "per_mchar": None,
        "per_request": None,
    },
    ("whisper", "base"): {
        "input_per_mtok": 0.0,
        "output_per_mtok": 0.0,
        "cache_read_per_mtok": 0.0,
        "cache_write_per_mtok": 0.0,
        "per_mchar": None,
        "per_request": None,
    },
}
BUDGET_MONTH_USD = 1500.0

TICKETS: list[dict[str, Any]] = [
    {
        "reason": "sign_in",
        "subject": "Can't sign in after changing my password",
        "message": "I changed my password on my laptop and now my phone says my session ended. When I sign in on the phone it says the password is wrong, but it works on the laptop.",
        "reply": "Thanks {first_name}. Changing your password signs you out everywhere else on purpose. Could you check the phone isn't filling in the old password from its keychain? Type it in by hand once and it should stick.",
        "follow": "That was it, the keychain had the old one. Thank you!",
        "tags": ["password"],
    },
    {
        "reason": "upload",
        "subject": "PDF stuck on 'Reading your file'",
        "message": "I uploaded my lecture slides as a PDF (about 40 pages) and it has been on 'Reading your file' for twenty minutes. Other PDFs worked yesterday.",
        "reply": "Hi {first_name}, sorry about that. Some PDFs made from scans take much longer. Could you tell us roughly how big the file is? You can also try splitting it in two.",
        "follow": "It's 180 MB, it's scans of handwritten notes.",
        "note": "Scanned 180 MB PDF: over the upload limit in practice. Suggest compressing.",
        "tags": ["pdf"],
    },
    {
        "reason": "teach",
        "subject": "No voice in Teach mode on Safari",
        "message": "Teach mode starts and the pointer moves but there's no voice at all. I'm on Safari on a Mac. Chrome works.",
        "reply": "Thanks {first_name}. Safari blocks sound until you've clicked on the page once. Click anywhere on the lesson after it starts, and the voice should come in. Does that help?",
        "note": "Known Safari autoplay issue. Tracked with the web team.",
        "tags": ["safari", "audio"],
    },
    {
        "reason": "notes",
        "subject": "Flashcards for one section repeat the same card",
        "message": "The flashcards for one section show the same card three times with slightly different wording.",
        "reply": "Thanks for flagging this, {first_name}. Could you tell us which session it was (the name is enough)? We'll look at why it repeated.",
        "tags": ["flashcards"],
    },
    {
        "reason": "pictures",
        "subject": "Wrong picture on the board",
        "message": "During a lesson the board showed a picture that had nothing to do with the topic. It went away on the next step.",
        "reply": "Sorry {first_name}, that picture shouldn't have been chosen. We've blocked it so it won't come back.",
        "note": "Blocked the picture from the moderation list.",
        "tags": ["pictures"],
    },
    {
        "reason": "slow",
        "subject": "Dashboard takes a minute to load",
        "message": "The dashboard takes about a minute to show my sessions. It used to be instant. I have maybe 60 sessions.",
        "reply": "Thanks {first_name}. We've found a slow query for accounts with many sessions and a fix is on its way this week.",
        "follow": "Still slow today, just so you know.",
        "tags": ["performance"],
    },
    {
        "reason": "family",
        "subject": "My child's PIN is locked",
        "message": "My son typed the wrong PIN too many times and now it says locked. How do I reset it? I'm the parent account.",
        "reply": "Hi {first_name}. As the guardian you can reset the PIN from Family, then the child's card, then Reset PIN. The lock also clears by itself after 15 minutes.",
        "tags": ["pin"],
    },
    {
        "reason": "study_tools",
        "subject": "Highlights gone after refresh",
        "message": "I highlighted a few lines in my notes, refreshed the page, and they're gone.",
        "reply": "Thanks {first_name}. Were you signed in on two tabs at the same time? We've seen highlights from one tab overwrite the other.",
        "follow": "Yes, I had two tabs open.",
        "tags": ["highlights", "bug"],
    },
    {
        "reason": "account",
        "subject": "Move me to my school's account",
        "message": "My school uses AnotherNote now. Can my account join the school, so my teacher can see it?",
        "reply": "Hi {first_name}. Your school's admin can invite you with the email you use here; once you accept, your account joins the school and keeps your sessions.",
        "tags": ["organisation"],
    },
    {
        "reason": "idea",
        "subject": "A timer option for quizzes",
        "message": "It would be great to have a timer on quizzes so I can practise for exams under time pressure.",
        "reply": "Love this idea, {first_name}. We've added it to our list.",
        "tags": ["feature-request"],
    },
    {
        "reason": "other",
        "subject": "Can I download all my notes?",
        "message": "Is there a way to download everything I've written, in case I change laptops?",
        "reply": "Hi {first_name}. Your notes live in your account, not on the laptop, so a new laptop has them as soon as you sign in. A download of everything is on our list.",
        "tags": ["export"],
    },
    {
        "reason": "upload",
        "subject": "Word document shows blank pages",
        "message": "I uploaded a Word file and the PDF view shows blank pages where the diagrams should be.",
        "reply": "Thanks {first_name}. Some diagrams drawn inside Word don't survive the conversion. Could you save it as PDF from Word and upload that instead?",
        "tags": ["docx"],
    },
    {
        "reason": "teach",
        "subject": "The mic doesn't hear me",
        "message": "When I hold the key to ask a question, the mic icon lights up but it never hears anything.",
        "reply": "Hi {first_name}, could you check that the browser has permission to use the microphone for this site? It's in the address bar, left of the address.",
        "tags": ["microphone"],
    },
    {
        "reason": "sign_in",
        "subject": "Signing in with Microsoft loops back",
        "message": "When I sign in with Microsoft it takes me back to the sign-in page again and again.",
        "note": "School enforces SSO with Google, not Microsoft. Ask them to use Google.",
        "tags": ["sso"],
    },
    {
        "reason": "slow",
        "subject": "Lesson stops halfway",
        "message": "Teach mode stops in the middle of the lesson and the spinner keeps going.",
        "tags": ["teach"],
    },
    {
        "reason": "notes",
        "subject": "Quiz answer marked wrong but it's right",
        "message": "A multiple choice question marked my answer wrong, but the explanation says my answer is right.",
        "reply": "Thanks {first_name}, you're right, and sorry. We've fixed the question.",
        "tags": ["quiz"],
    },
]
CANARY = "CANARY-7f3a-DO-NOT-LEAK"
PAGES = [
    ("/dashboard", 30),
    ("/dashboard/:id/full-study", 25),
    ("/dashboard/note/:id", 15),
    ("/dashboard/note/new", 4),
    ("/dashboard/folders", 6),
    ("/dashboard/folder/:n", 4),
    ("/dashboard/calendar", 4),
    ("/dashboard/settings", 3),
    ("/dashboard/profile", 3),
    ("/dashboard/help", 2),
    ("/dashboard/family", 2),
]
ACTIONS = [
    ("study_view", 12),
    ("teach_start", 10),
    ("teach_end", 8),
    ("pdf_open_timing", 5),
    ("session_created", 4),
    ("pdf_quiz_start", 3),
    ("pdf_quiz_complete", 2),
    ("desktop_handoff", 0.5),
]
# (message, page, weight): what goes wrong day to day
ERRORS = [
    ("API unreachable GET /api/app-data", "/dashboard", 5),
    ("TypeError: Cannot read properties of undefined (reading 'map')", "/dashboard/:id/full-study", 4),
    (
        "NotAllowedError: play() failed because the user didn't interact with the document first.",
        "/dashboard/:id/full-study",
        4,
    ),
    ("API 429 POST /api/study-sessions/:id/questions/more", "/dashboard/:id/full-study", 2),
    (
        "QuotaExceededError: Failed to execute 'setItem' on 'Storage': Setting the value exceeded the quota.",
        "/dashboard/note/:id",
        1,
    ),
    ("Error: Invalid PDF structure.", "/dashboard/note/:id", 2),
]
CAMPAIGNS = [
    {"utm_source": "twitter", "utm_medium": "social", "utm_campaign": "back-to-school", "twclid": "2djh3kq9"},
    {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "september-digest"},
    {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "study-notes", "gclid": "Cj0KCQjw"},
    {"ref": "tester-priya"},
]
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


STAFF_NOTES = [
    "Checked the account: nothing unusual in sign-ins.",
    "Same report from two other people this week.",
    "Waiting for the web team's fix to ship.",
]


def masked_email(email: Optional[str]) -> Optional[str]:
    """As admin_users_v masks it: the first letter, then ***@ and the domain."""
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def masked_username(username: Optional[str]) -> Optional[str]:
    return f"{username[:3]}***" if username else None


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class User:
    id: int
    email: Optional[str]
    name: str
    username: Optional[str]
    account_kind: str
    role: Optional[str]
    org_id: Optional[int]
    org_role: Optional[str]
    auth_provider: Optional[str]
    birth_year: Optional[int]
    created_at: datetime
    last_login: Optional[datetime]
    last_seen_at: Optional[datetime]
    is_active: bool
    deleted_at: Optional[datetime]
    onboarding_completed: bool
    credentials_locked: bool
    pin_locked_until: Optional[datetime]
    xp: int
    token_epoch: int = 0
    engagement: float = 0.0
    footprint: dict[str, Any] = field(default_factory=dict)

    @property
    def first_name(self) -> str:
        return (self.name or "").split(" ")[0]

    @property
    def is_demo(self) -> bool:
        return (self.email or "").lower() in {
            "student@anothernotes.com",
            "demo@anothernotes.com",
            "student@playstudy.ai",
            "demo@playstudy.ai",
        }

    @property
    def status(self) -> str:
        if self.deleted_at:
            return "deleted"
        return "active" if self.is_active else "deactivated"


@dataclass
class Org:
    id: int
    name: str
    slug: str
    sso_provider: Optional[str]
    sso_enforced: bool
    created_at: datetime
    domains: list[tuple[str, bool]]


@dataclass
class Link:
    id: int
    guardian_id: int
    child_id: int
    origin: str
    status: str
    activated_at: Optional[datetime]
    revoked_at: Optional[datetime]


@dataclass
class Token:
    id: int
    user_id: int
    created_at: datetime
    expires_at: datetime
    blacklisted: bool
    device: Optional[dict[str, Any]]


@dataclass
class AuthEvent:
    id: int
    created_at: datetime
    user_id: Optional[int]
    kind: str
    method: Optional[str]
    reason: Optional[str]
    country: Optional[str]
    ua_family: Optional[str]
    ip_prefix_hash: Optional[str]
    identifier_hash: Optional[str]


@dataclass
class UsageDay:
    day: date
    user_id: Optional[int]
    feature: str
    provider: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    characters: int = 0
    audio_ms: int = 0
    cost_micro_usd: Optional[int] = None
    unpriced_calls: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Plan:
    id: str
    name: str
    description: str
    is_default: bool
    is_active: bool
    limits: dict[str, Any]
    price_cents: Optional[int]
    currency: Optional[str]
    interval: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class Assignment:
    id: int
    subject_type: str
    subject_id: int
    plan_id: str
    status: str
    source: str
    starts_at: datetime
    ends_at: Optional[datetime]
    note: Optional[str]
    assigned_by: Optional[str]
    created_at: datetime


@dataclass
class Message:
    id: int
    author: str
    staff_email: Optional[str]
    body: str
    internal: bool
    created_at: datetime


@dataclass
class Ticket:
    id: int
    user_id: int
    reason: str
    subject: str
    page_url: Optional[str]
    context: Optional[dict[str, str]]
    status: str
    priority: str
    assignee_email: Optional[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    last_user_at: Optional[datetime]
    last_staff_at: Optional[datetime]
    closed_at: Optional[datetime]
    messages: list[Message]

    @property
    def number(self) -> str:
        return f"AN-{self.id:04d}"


@dataclass
class Event:
    """A row of analytics_events, whole: what the admin API must NOT pass on is here too
    (data with its stack, the user agent, every tag), so tests can show it never does."""

    id: int
    created_at: datetime
    user_id: Optional[int]
    kind: str
    name: str
    path: Optional[str]
    tags: Optional[dict[str, str]]
    data: Optional[dict[str, Any]]
    user_agent: Optional[str]


@dataclass
class Outbox:
    id: int
    kind: str
    ticket_id: int
    created_at: datetime


@dataclass
class Audit:
    id: int
    at: datetime
    actor_email: str
    actor_role: str
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    reason: Optional[str]
    request_id: Optional[str]
    details: Optional[dict[str, Any]]


def cost_micro(provider: str, model: str, u: UsageDay) -> Optional[int]:
    price = PRICES.get((provider, model))
    if not price:
        return None
    total = 0.0
    parts = [
        (u.input_tokens - u.cache_read_tokens, price["input_per_mtok"]),
        (u.output_tokens, price["output_per_mtok"]),
        (u.cache_read_tokens, price["cache_read_per_mtok"]),
        (u.cache_write_tokens, price["cache_write_per_mtok"]),
        (u.characters, price["per_mchar"]),
    ]
    known = False
    for units, per_million in parts:
        if units <= 0:
            continue
        if per_million is None:
            return None
        total += units * per_million / 1_000_000
        known = True
    if provider == "whisper":
        known = True
    return round(total * 1_000_000) if known else None


class Store:
    """Everything the stub knows. Built once, then changed by the audited actions."""

    def __init__(self, now: Optional[datetime] = None, seed: int = 7):
        # The seed is written around `now`; queries ask current(), which is the real clock
        # unless a fixed time was given (the tests do).
        self.fixed_now = now
        self.now = (now or datetime.now(UTC)).replace(microsecond=0)
        self.today = self.now.date()
        self.rng = random.Random(seed)
        self.users: dict[int, User] = {}
        self.orgs: dict[int, Org] = {}
        self.links: list[Link] = []
        self.tokens: list[Token] = []
        self.auth_events: list[AuthEvent] = []
        self.activity: dict[tuple[int, date], int] = {}
        self.usage: list[UsageDay] = []
        self.plans: dict[str, Plan] = {}
        self.assignments: list[Assignment] = []
        self.tickets: dict[int, Ticket] = {}
        self.outbox: list[Outbox] = []
        self.audit: list[Audit] = []
        self.events: list[Event] = []
        self._ids: dict[str, int] = {}
        self._seed()

    def current(self) -> datetime:
        return self.fixed_now or datetime.now(UTC).replace(microsecond=0)

    def next_id(self, kind: str) -> int:
        self._ids[kind] = self._ids.get(kind, 0) + 1
        return self._ids[kind]

    def at(self, days_ago: float = 0.0, hours: float = 0.0, minutes: float = 0.0) -> datetime:
        return (self.now - timedelta(days=days_ago, hours=hours, minutes=minutes)).replace(microsecond=0)

    # --- the seed ------------------------------------------------------------------------
    def _seed(self) -> None:
        self._seed_orgs()
        self._seed_users()
        self._seed_family()
        self._seed_activity_and_sign_ins()
        self._seed_attacks()
        self._seed_sessions()
        self._seed_usage()
        self._seed_plans()
        self._seed_tickets()
        self._seed_audit()
        self._seed_analytics()
        self._whole_seconds()

    def _whole_seconds(self) -> None:
        def trim(value: Any) -> Any:
            return value.replace(microsecond=0) if isinstance(value, datetime) else value

        for collection in (
            self.users.values(),
            self.tokens,
            self.auth_events,
            self.links,
            self.assignments,
            self.outbox,
            self.audit,
            self.tickets.values(),
            self.events,
        ):
            for item in collection:
                for name, value in vars(item).items():
                    if isinstance(value, datetime):
                        setattr(item, name, trim(value))
        for token in self.tokens:
            if token.device:
                token.device["last_refresh_at"] = trim(token.device["last_refresh_at"])
        for ticket in self.tickets.values():
            for m in ticket.messages:
                m.created_at = trim(m.created_at)

    def _seed_orgs(self) -> None:
        for name, slug, sso, enforced, domains in ORGS:
            oid = self.next_id("org")
            self.orgs[oid] = Org(oid, name, slug, sso, enforced, self.at(self.rng.randint(120, 400)), domains)

    def _new_user(self, **kw: Any) -> User:
        uid = self.next_id("user")
        rng = self.rng
        created = kw.pop("created_at", self.at(rng.uniform(1, 200)))
        engagement = kw.pop("engagement", rng.random() ** 2)
        user = User(
            id=uid,
            created_at=created,
            last_login=None,
            last_seen_at=None,
            is_active=True,
            deleted_at=None,
            onboarding_completed=kw.pop("onboarding_completed", rng.random() > 0.07),
            credentials_locked=False,
            pin_locked_until=None,
            xp=0,
            engagement=engagement,
            **kw,
        )
        self.users[uid] = user
        return user

    def _seed_users(self) -> None:
        rng = self.rng
        self._new_user(
            email="student@anothernotes.com",
            name="Demo Student",
            username=None,
            account_kind="standard",
            role="student",
            org_id=None,
            org_role=None,
            auth_provider="password",
            birth_year=None,
            created_at=self.at(300),
            engagement=0.3,
        )
        self._new_user(
            email="demo@anothernotes.com",
            name="Demo Teacher",
            username=None,
            account_kind="standard",
            role="teacher",
            org_id=None,
            org_role=None,
            auth_provider="password",
            birth_year=None,
            created_at=self.at(300),
            engagement=0.1,
        )
        for _ in range(232):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            org_id: Optional[int] = None
            org_role = None
            roll = rng.random()
            if roll < 0.12:
                role = "teacher"
                if rng.random() < 0.7:
                    org_id = rng.randint(1, len(ORGS))
                    org_role = "owner" if rng.random() < 0.08 else ("admin" if rng.random() < 0.2 else "member")
            elif roll < 0.92:
                role = "student"
                if rng.random() < 0.25:
                    org_id = rng.randint(1, len(ORGS))
                    org_role = "member"
            else:
                role = None
            if org_id:
                domain = self.orgs[org_id].domains[0][0]
            else:
                domain = rng.choice(PERSONAL_DOMAINS)
            email = f"{first.lower()}.{last.lower()}{rng.randint(1, 999)}@{domain}"
            provider = rng.choices(["password", "google", "microsoft"], [60, 30, 10])[0]
            if org_id and self.orgs[org_id].sso_provider in ("google", "microsoft"):
                provider = self.orgs[org_id].sso_provider
            birth_year = None
            if role == "student" and rng.random() < 0.6:
                birth_year = self.today.year - rng.randint(13, 24)
            self._new_user(
                email=email,
                name=f"{first} {last}",
                username=None,
                account_kind="standard",
                role=role,
                org_id=org_id,
                org_role=org_role,
                auth_provider=provider,
                birth_year=birth_year,
            )
        for _ in range(38):
            first = rng.choice(FIRST)
            username = f"{first.lower()}-{''.join(rng.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(4))}"
            child = self._new_user(
                email=None,
                name=first,
                username=username,
                account_kind="managed_child",
                role="student",
                org_id=None,
                org_role=None,
                auth_provider=None,
                birth_year=self.today.year - rng.randint(7, 12),
            )
            child.credentials_locked = True
        standard = [u for u in self.users.values() if u.account_kind == "standard" and not u.is_demo]
        for u in rng.sample(standard, 4):
            u.is_active = False
        for u in rng.sample([u for u in standard if u.is_active], 2):
            u.deleted_at = self.at(rng.uniform(2, 20))
            u.is_active = False
        children = [u for u in self.users.values() if u.account_kind == "managed_child"]
        for u in rng.sample(children, 2):
            u.pin_locked_until = self.now + timedelta(minutes=rng.randint(3, 14))
        for u in self.users.values():
            u.xp = int(u.engagement * rng.randint(200, 9000))
            fp_scale = u.engagement
            pdfs = int(fp_scale * rng.randint(0, 30))
            u.footprint = {
                "study_sessions": int(fp_scale * rng.randint(1, 60)) + 1,
                "notes": int(fp_scale * rng.randint(0, 90)),
                "youtube_sessions": int(fp_scale * rng.randint(0, 12)),
                "pdfs": pdfs,
                "office_files": int(fp_scale * rng.randint(0, 8)),
                "pdf_bytes": pdfs * rng.randint(900_000, 14_000_000),
                "highlights": int(fp_scale * rng.randint(0, 300)),
                "sticky_notes": int(fp_scale * rng.randint(0, 40)),
                "answers": int(fp_scale * rng.randint(0, 2500)),
            }

    def _seed_family(self) -> None:
        rng = self.rng
        adults = [
            u
            for u in self.users.values()
            if u.account_kind == "standard" and u.role != "teacher" and not u.is_demo and u.status == "active"
        ]
        guardians = rng.sample(adults, 26)
        for child in (u for u in self.users.values() if u.account_kind == "managed_child"):
            g = rng.choice(guardians)
            self.links.append(Link(self.next_id("link"), g.id, child.id, "created", "active", child.created_at, None))
            if rng.random() < 0.3:
                g2 = rng.choice([x for x in guardians if x.id != g.id])
                self.links.append(
                    Link(
                        self.next_id("link"),
                        g2.id,
                        child.id,
                        "created",
                        "active",
                        child.created_at + timedelta(days=1),
                        None,
                    )
                )
        teens = [u for u in adults if u.birth_year and self.today.year - u.birth_year < 18 and u not in guardians]
        for teen in rng.sample(teens, min(8, len(teens))):
            g = rng.choice(guardians)
            revoked = rng.random() < 0.25
            activated = teen.created_at + timedelta(days=rng.randint(1, 20))
            self.links.append(
                Link(
                    self.next_id("link"),
                    g.id,
                    teen.id,
                    "claimed",
                    "revoked" if revoked else "active",
                    activated,
                    activated + timedelta(days=rng.randint(5, 30)) if revoked else None,
                )
            )

    def _user_ua(self, user: User) -> str:
        return UA[user.id * 7 % len(UA)] if self.rng.random() < 0.8 else self.rng.choices(UA, UA_WEIGHTS)[0]

    def _user_country(self, user: User) -> str:
        return (
            COUNTRIES[user.id * 13 % 3] if self.rng.random() < 0.9 else self.rng.choices(COUNTRIES, COUNTRY_WEIGHTS)[0]
        )

    def _auth(
        self,
        when: datetime,
        user_id: Optional[int],
        kind: str,
        method: Optional[str] = None,
        reason: Optional[str] = None,
        **kw: Any,
    ) -> AuthEvent:
        event = AuthEvent(
            0,
            when,
            user_id,
            kind,
            method,
            reason,
            kw.get("country"),
            kw.get("ua_family"),
            kw.get("ip_prefix_hash"),
            kw.get("identifier_hash"),
        )
        self.auth_events.append(event)
        return event

    def _method(self, user: User) -> str:
        if user.account_kind == "managed_child":
            return "pin"
        if self.rng.random() < 0.06:
            return "desktop"
        return {"google": "google", "microsoft": "microsoft"}.get(user.auth_provider or "", "password")

    def _seed_activity_and_sign_ins(self) -> None:
        rng = self.rng
        for user in self.users.values():
            if user.status == "deleted":
                continue
            p_active = 0.04 + 0.7 * user.engagement
            network = short_hash(f"net-{user.id}")
            last_active: Optional[datetime] = None
            for days_ago in range(89, -1, -1):
                day = self.today - timedelta(days=days_ago)
                start = datetime(day.year, day.month, day.day, tzinfo=UTC)
                if start < user.created_at.replace(hour=0, minute=0, second=0) or rng.random() > p_active:
                    continue
                if days_ago == 0 and self.now.hour < 1:
                    continue
                seconds = int(rng.uniform(120, 5400) * (0.4 + user.engagement))
                self.activity[(user.id, day)] = seconds
                latest_hour = self.now.hour if days_ago == 0 else 23
                when = start + timedelta(
                    hours=rng.randint(min(7, latest_hour), latest_hour), minutes=rng.randint(0, 59)
                )
                if when > self.now:
                    when = self.now - timedelta(minutes=rng.randint(1, 50))
                last_active = when
                if days_ago > 30 or not user.is_active:
                    continue
                ua, country = self._user_ua(user), self._user_country(user)
                for _ in range(rng.choices([0, 1, 2], [15, 60, 25])[0]):
                    self._auth(
                        when - timedelta(minutes=rng.randint(0, 30)),
                        user.id,
                        "sign_in",
                        self._method(user),
                        country=country,
                        ua_family=ua,
                        ip_prefix_hash=network,
                    )
                    user.last_login = max(user.last_login or when, when)
                if rng.random() < 0.05:
                    method = self._method(user)
                    self._auth(
                        when - timedelta(minutes=rng.randint(31, 90)),
                        user.id,
                        "sign_in_failed",
                        method,
                        "wrong_password" if method != "pin" else "wrong_pin",
                        country=country,
                        ua_family=ua,
                        ip_prefix_hash=network,
                        identifier_hash=short_hash(f"id-{user.id}"),
                    )
                if rng.random() < 0.08:
                    self._auth(
                        when + timedelta(minutes=rng.randint(10, 120)),
                        user.id,
                        "sign_out",
                        None,
                        country=country,
                        ua_family=ua,
                        ip_prefix_hash=network,
                    )
                if user.account_kind == "managed_child" and rng.random() < 0.02:
                    self._auth(
                        when,
                        user.id,
                        "pin_locked",
                        "pin",
                        "locked",
                        country=country,
                        ua_family=ua,
                        ip_prefix_hash=network,
                    )
                    self._auth(
                        when + timedelta(minutes=20),
                        user.id,
                        "pin_reset",
                        None,
                        country=country,
                        ua_family=ua,
                        ip_prefix_hash=network,
                    )
                if rng.random() < 0.004:
                    self._auth(
                        when, user.id, "password_changed", None, country=country, ua_family=ua, ip_prefix_hash=network
                    )
                if rng.random() < 0.002:
                    self._auth(
                        when,
                        user.id,
                        "refresh_replay",
                        None,
                        country=self.rng.choice(COUNTRIES),
                        ua_family=ua,
                        ip_prefix_hash=short_hash(f"replay-{user.id}"),
                    )
            if last_active:
                user.last_seen_at = last_active
                user.last_login = user.last_login or last_active - timedelta(hours=rng.randint(0, 4))
        # People on the site right now, and a few in the last hour.
        recent = sorted(
            (u for u in self.users.values() if u.status == "active" and (u.id, self.today) in self.activity),
            key=lambda u: -u.engagement,
        )
        for u in recent[:17]:
            u.last_seen_at = self.now - timedelta(seconds=rng.randint(5, 280))
        for u in recent[17:40]:
            u.last_seen_at = self.now - timedelta(minutes=rng.randint(6, 90))
        for u in self.users.values():
            if u.pin_locked_until:
                self._auth(
                    u.pin_locked_until - timedelta(minutes=15),
                    u.id,
                    "pin_locked",
                    "pin",
                    "locked",
                    country="GB",
                    ua_family="Safari · iOS",
                    ip_prefix_hash=short_hash(f"net-{u.id}"),
                )

    def _seed_attacks(self) -> None:
        """Three networks trying many addresses: what credential stuffing looks like."""
        rng = self.rng
        for n, (country, size, days_ago) in enumerate([("NL", 140, 1.2), ("US", 60, 4.5), ("SG", 35, 12.0)]):
            network = short_hash(f"attack-{n}")
            start = self.at(days_ago)
            identifiers = [short_hash(f"attack-{n}-id-{i}") for i in range(size // 3)]
            for i in range(size):
                when = start + timedelta(minutes=i * rng.uniform(0.2, 1.5))
                if when > self.now:
                    break
                reason = rng.choices(["no_account", "wrong_password", "locked"], [60, 36, 4])[0]
                self._auth(
                    when,
                    None if reason == "no_account" else rng.choice(list(self.users)),
                    "sign_in_failed",
                    "password",
                    reason,
                    country=country,
                    ua_family="Chrome · Linux",
                    ip_prefix_hash=network,
                    identifier_hash=rng.choice(identifiers),
                )
        self.auth_events.sort(key=lambda e: e.created_at)
        for i, event in enumerate(self.auth_events, start=1):
            event.id = i
        self._ids["auth"] = len(self.auth_events)

    def _seed_sessions(self) -> None:
        rng = self.rng
        for user in self.users.values():
            if user.status != "active" or not user.last_seen_at or self.now - user.last_seen_at > timedelta(days=30):
                continue
            for _ in range(rng.choices([1, 2, 3, 4], [50, 30, 15, 5])[0]):
                created = max(user.created_at, user.last_seen_at - timedelta(days=rng.uniform(0, 25)))
                device = None
                if rng.random() < 0.8:
                    device = {
                        "ua_family": self._user_ua(user),
                        "country": self._user_country(user),
                        "method": self._method(user),
                        "last_refresh_at": min(self.now, created + timedelta(hours=rng.uniform(0, 200))),
                    }
                self.tokens.append(
                    Token(self.next_id("token"), user.id, created, created + timedelta(days=30), False, device)
                )
            if rng.random() < 0.3:
                created = user.last_seen_at - timedelta(days=rng.uniform(5, 40))
                self.tokens.append(
                    Token(self.next_id("token"), user.id, created, created + timedelta(days=30), True, None)
                )

    def _seed_usage(self) -> None:
        rng = self.rng
        rows: dict[tuple[date, int, str, str, str], UsageDay] = {}
        yesterday = self.today - timedelta(days=1)
        # Two people with an ordinary habit have a very unusual day yesterday, so the
        # "Unusual days" list has something to show. They must have been active that day.
        active_yesterday = sorted(uid for (uid, day) in self.activity if day == yesterday)
        candidates = [
            uid
            for uid in active_yesterday
            if 0.2 < self.users[uid].engagement < 0.7 and self.users[uid].status == "active"
        ]
        spikes = set(rng.sample(candidates, min(2, len(candidates))))
        for (user_id, day), _seconds in self.activity.items():
            if (self.today - day).days > 60:
                continue
            user = self.users[user_id]
            for feature, weight, providers, units in FEATURES:
                if rng.random() > weight * (0.6 + user.engagement):
                    continue
                ((provider, model),) = rng.choices([p for p, _ in providers], [s for _, s in providers])
                key = (day, user_id, feature, provider, model)
                row = rows.get(key) or UsageDay(day, user_id, feature, provider, model)
                rows[key] = row
                calls = rng.randint(*units["calls"])
                boost = 12 if user_id in spikes and day == yesterday else 1
                for _ in range(calls * boost):
                    row.calls += 1
                    if "input" in units:
                        inp = rng.randint(*units["input"])
                        row.input_tokens += inp
                        row.output_tokens += rng.randint(*units["output"])
                        if provider in ("deepseek", "anthropic") and rng.random() < 0.5:
                            row.cache_read_tokens += int(inp * rng.uniform(0.3, 0.7))
                        if provider == "anthropic" and rng.random() < 0.2:
                            row.cache_write_tokens += int(inp * 0.3)
                    if "characters" in units:
                        row.characters += rng.randint(*units["characters"])
                    if "audio_ms" in units:
                        row.audio_ms += rng.randint(*units["audio_ms"])
        for row in rows.values():
            row.cost_micro_usd = cost_micro(row.provider, row.model, row)
            row.unpriced_calls = row.calls if row.cost_micro_usd is None else 0
            self.usage.append(row)
        self.usage.sort(key=lambda r: (r.day, r.user_id or 0, r.feature))

    def _seed_plans(self) -> None:
        created = self.at(4)
        for pid, name, desc, default in [
            ("free", "Free", "Everyone starts here.", True),
            ("plus", "Plus", "For one person who studies a lot.", False),
            ("family", "Family", "For a guardian and the children linked to them.", False),
            ("school", "School", "For a school or district, through its organisation.", False),
        ]:
            self.plans[pid] = Plan(pid, name, desc, default, True, {}, None, None, None, created, created)
        rng = self.rng
        for oid in (1, 2, 3):
            self.assignments.append(
                Assignment(
                    self.next_id("assignment"),
                    "organization",
                    oid,
                    "school",
                    "active",
                    "manual",
                    self.at(3),
                    None,
                    "School agreement",
                    "leo@anothernote.app",
                    self.at(3),
                )
            )
        standard = [
            u for u in self.users.values() if u.account_kind == "standard" and u.status == "active" and not u.org_id
        ]
        for u in rng.sample(standard, 14):
            status = "trial" if rng.random() < 0.2 else "active"
            start = self.at(rng.uniform(0.5, 3.5))
            if rng.random() < 0.3:
                old_start = start - timedelta(days=rng.randint(20, 60))
                self.assignments.append(
                    Assignment(
                        self.next_id("assignment"),
                        "user",
                        u.id,
                        "plus",
                        "expired",
                        "promo",
                        old_start,
                        start,
                        "Launch promo",
                        "maya@anothernote.app",
                        old_start,
                    )
                )
            self.assignments.append(
                Assignment(
                    self.next_id("assignment"),
                    "user",
                    u.id,
                    "plus",
                    status,
                    rng.choice(["manual", "promo"]),
                    start,
                    start + timedelta(days=14) if status == "trial" else None,
                    rng.choice(["Asked for more Teach mode", "Beta tester", "Support goodwill"]),
                    rng.choice(["leo@anothernote.app", "maya@anothernote.app"]),
                    start,
                )
            )
        guardians = {link.guardian_id for link in self.links if link.origin == "created"}
        for gid in rng.sample(sorted(guardians), 6):
            start = self.at(rng.uniform(0.5, 3.5))
            self.assignments.append(
                Assignment(
                    self.next_id("assignment"),
                    "user",
                    gid,
                    "family",
                    "active",
                    "manual",
                    start,
                    None,
                    "Family with two children",
                    "leo@anothernote.app",
                    start,
                )
            )

    def _seed_tickets(self) -> None:
        rng = self.rng
        people = [
            u for u in self.users.values() if u.status != "deleted" and u.account_kind == "standard" and not u.is_demo
        ]
        plan: list[tuple[str, int]] = [
            ("open", 6),
            ("waiting_on_us", 5),
            ("waiting_on_user", 7),
            ("resolved", 18),
            ("closed", 12),
        ]
        statuses = [s for s, n in plan for _ in range(n)]
        rng.shuffle(statuses)
        created_times = sorted(self.at(rng.uniform(0.02, 45)) for _ in statuses)
        for created, status in zip(created_times, statuses, strict=False):
            if status in ("open", "waiting_on_us") and self.now - created > timedelta(days=4):
                created = self.at(rng.uniform(0.05, 3.5))
            template = rng.choice(TICKETS)
            user = rng.choice(people)
            self._make_ticket(user, template, created, status)
        # Keep ids in creation order, like a database sequence.
        ordered = sorted(self.tickets.values(), key=lambda t: t.created_at)
        self.tickets = {}
        self.outbox = []
        self._ids["ticket"] = 0
        for t in ordered:
            t.id = self.next_id("ticket")
            self.tickets[t.id] = t
        events = []
        for t in self.tickets.values():
            events.append((t.created_at, "ticket.created", t.id))
            for m in t.messages[1:]:
                if m.author == "user":
                    events.append((m.created_at, "ticket.user_replied", t.id))
        for when, kind, tid in sorted(events):
            self.outbox.append(Outbox(self.next_id("outbox"), kind, tid, when))

    def _make_ticket(self, user: User, template: dict[str, Any], created: datetime, status: str) -> Ticket:
        rng = self.rng
        staff = rng.choice(["maya@anothernote.app", "ines@anothernote.app", "leo@anothernote.app"])
        first = user.first_name
        messages = [Message(self.next_id("message"), "user", None, template["message"], False, created)]
        t = created
        last_user, last_staff = created, None
        if status != "open":
            if template.get("note") and rng.random() < 0.7:
                t += timedelta(minutes=rng.randint(10, 300))
                messages.append(Message(self.next_id("message"), "staff", staff, template["note"], True, t))
            if status in ("waiting_on_us", "waiting_on_user", "resolved", "closed"):
                reply = (
                    template.get("reply") or "Thanks {first_name}, we're looking into this and will write back soon."
                )
                t += timedelta(minutes=rng.randint(20, 600))
                messages.append(
                    Message(self.next_id("message"), "staff", staff, reply.format(first_name=first), False, t)
                )
                last_staff = t
            if status == "waiting_on_us" or (
                status in ("resolved", "closed") and template.get("follow") and rng.random() < 0.5
            ):
                t += timedelta(minutes=rng.randint(30, 900))
                messages.append(
                    Message(
                        self.next_id("message"), "user", None, template.get("follow") or "Any news on this?", False, t
                    )
                )
                last_user = t
            if status in ("resolved", "closed") and rng.random() < 0.3:
                t += timedelta(minutes=rng.randint(5, 60))
                messages.append(Message(self.next_id("message"), "staff", staff, rng.choice(STAFF_NOTES), True, t))
            if status == "closed" and rng.random() < 0.5 and t + timedelta(days=7) < self.current():
                t += timedelta(days=7)
                messages.append(
                    Message(self.next_id("message"), "system", None, "Closed after 7 days without a reply.", False, t)
                )
        now = self.current()
        if t > now:
            t = now - timedelta(minutes=2) if created < now - timedelta(minutes=2) else created
        for m in messages:
            m.created_at = min(m.created_at, t)
        last_user = min(last_user, t)
        last_staff = min(last_staff, t) if last_staff else None
        ticket = Ticket(
            id=self.next_id("ticket"),
            user_id=user.id,
            reason=template["reason"],
            subject=template["subject"],
            page_url=rng.choice(["/dashboard", "/study/full", "/study/teach", "/settings/family", "/notes", "/upload"]),
            context={
                "browser": self._user_ua(user),
                "language": rng.choice(["en-GB", "en-US", "en-IE"]),
                "viewport": rng.choice(["1440x900", "1920x1080", "390x844", "1280x800"]),
                "timezone": rng.choice(["Europe/London", "America/New_York", "Europe/Dublin", "America/Chicago"]),
                "app_version": rng.choice(["2026.09.24", "2026.09.19", "2026.09.11"]),
                "session_id": f"{rng.getrandbits(32):08x}-{rng.getrandbits(16):04x}-{rng.getrandbits(16):04x}",
                "from": rng.choice(["/dashboard", "/study/full", "/help"]),
            },
            status=status,
            priority=rng.choices(["low", "normal", "high", "urgent"], [15, 60, 20, 5])[0],
            assignee_email=None if status == "open" and rng.random() < 0.8 else staff,
            tags=list(template.get("tags", [])),
            created_at=created,
            updated_at=t,
            last_user_at=last_user,
            last_staff_at=last_staff,
            closed_at=t if status in ("resolved", "closed") else None,
            messages=messages,
        )
        self.tickets[ticket.id] = ticket
        return ticket

    def _seed_audit(self) -> None:
        rng = self.rng
        seeded = []
        for _ in range(80):
            actor, role = rng.choice(STAFF[:3])
            action = rng.choices(
                [
                    "view.overview",
                    "view.users",
                    "view.user",
                    "user.reveal_email",
                    "ticket.view",
                    "ticket.reply",
                    "ticket.update",
                    "plan.assign",
                    "user.sign_out_everywhere",
                ],
                [20, 15, 25, 4, 15, 10, 6, 3, 2],
            )[0]
            target_type, target_id, reason, details = None, None, None, None
            if action in ("view.user", "user.reveal_email", "user.sign_out_everywhere", "plan.assign"):
                target_type, target_id = "user", str(rng.choice(list(self.users)))
            if action.startswith("ticket.") and self.tickets:
                target_type, target_id = "ticket", str(rng.choice(list(self.tickets)))
            if action == "user.reveal_email":
                reason = rng.choice(
                    [
                        "Replying to their ticket by email",
                        "Guardian asked us to confirm the account",
                        "Checking a school's SSO problem",
                    ]
                )
            if action == "user.sign_out_everywhere":
                reason = "Lost phone, asked us to sign out everywhere"
                details = {"sessions_ended": rng.randint(1, 4)}
            if action == "plan.assign":
                reason = "Support goodwill"
                details = {"plan_id": "plus", "status": "active"}
            if action == "ticket.update":
                details = {"fields": ["status"]}
            seeded.append((self.at(rng.uniform(0, 14)), actor, role, action, target_type, target_id, reason, details))
        for at, actor, role, action, ttype, tid, reason, details in sorted(seeded):
            self.audit.append(
                Audit(
                    self.next_id("audit"),
                    at,
                    actor,
                    role,
                    action,
                    ttype,
                    tid,
                    reason,
                    f"{rng.getrandbits(128):032x}",
                    details,
                )
            )

    def _seed_analytics(self) -> None:
        """Page views, actions and errors for the last 30 days, and two bad days."""
        rng = self.rng
        raw: list[
            tuple[datetime, Optional[int], str, str, Optional[str], Optional[dict[str, str]], Optional[dict[str, Any]]]
        ] = []

        def stack(message: str) -> dict[str, Any]:
            # What the browser really sends with an error. It stays in the table.
            return {
                "stack": f"{message}\n    at render (NotePage.tsx:120:15)\n    at {CANARY} (chunk-3f2a.js:1:2048)",
                "status": 502,
            }

        def page_path(template: str) -> str:
            return template.replace(
                ":id",
                f"{rng.getrandbits(32):08x}-{rng.getrandbits(16):04x}-4{rng.getrandbits(12):03x}-a{rng.getrandbits(12):03x}-{rng.getrandbits(48):012x}",
            ).replace(":n", str(rng.randint(1, 400)))

        for (user_id, day), _seconds in self.activity.items():
            age = (self.today - day).days
            if age > 30:
                continue
            start = datetime(day.year, day.month, day.day, tzinfo=UTC)
            latest = self.now.hour if age == 0 else 23
            hour = rng.randint(min(7, latest), latest)
            first_tags = rng.choice(CAMPAIGNS) if rng.random() < 0.04 else None
            for i in range(rng.randint(3, 10)):
                when = start + timedelta(hours=hour, minutes=rng.randint(0, 59), seconds=i * 30)
                template = rng.choices([p for p, _ in PAGES], [w for _, w in PAGES])[0]
                raw.append((when, user_id, "view", template, page_path(template), first_tags, None))
            for _ in range(rng.choices([0, 1, 2, 3, 4], [30, 30, 20, 12, 8])[0]):
                when = start + timedelta(hours=hour, minutes=rng.randint(0, 59))
                name = rng.choices([a for a, _ in ACTIONS], [w for _, w in ACTIONS])[0]
                raw.append(
                    (
                        when,
                        user_id,
                        "action",
                        name,
                        page_path("/dashboard/:id/full-study"),
                        first_tags,
                        {"ms": rng.randint(50, 4000)},
                    )
                )
            if rng.random() < 0.08:
                message, template, _ = rng.choices(ERRORS, [w for *_, w in ERRORS])[0]
                when = start + timedelta(hours=hour, minutes=rng.randint(0, 59))
                raw.append((when, user_id, "error", message, page_path(template), first_tags, stack(message)))
        # People arriving from links, before they sign in.
        for _ in range(900):
            when = self.at(rng.uniform(0, 30))
            tags = rng.choice(CAMPAIGNS) if rng.random() < 0.5 else None
            raw.append((when, None, "view", "/", "/", tags, None))
            if rng.random() < 0.3:
                raw.append((when + timedelta(seconds=40), None, "view", "/auth", "/auth", tags, None))
        # Two bad days: a provider outage yesterday afternoon, and a deploy three days ago
        # that left open tabs asking for files that no longer existed.
        people = [u.id for u in self.users.values() if u.status == "active"]
        outage = datetime.combine(self.today - timedelta(days=1), datetime.min.time(), tzinfo=UTC) + timedelta(hours=14)
        for _ in range(140):
            when = outage + timedelta(minutes=rng.uniform(0, 110))
            message = "API 502 POST /api/study-sessions/:id/guide/script"
            raw.append(
                (
                    when,
                    rng.choice(people),
                    "error",
                    message,
                    page_path("/dashboard/:id/full-study"),
                    None,
                    stack(message),
                )
            )
        deploy = self.at(3, hours=5)
        for _ in range(60):
            when = deploy + timedelta(minutes=rng.uniform(0, 240))
            message = "TypeError: Failed to fetch dynamically imported module: https://anothernote.app/assets/NotePage-3f2a91.js"
            raw.append(
                (when, rng.choice(people), "error", message, page_path("/dashboard/note/:id"), None, stack(message))
            )
        raw = [r for r in raw if r[0] <= self.now]
        raw.sort(key=lambda r: r[0])
        self.events = [
            Event(i, when, uid, kind, name[:160], path, dict(tags) if tags else None, data, AGENT)
            for i, (when, uid, kind, name, path, tags, data) in enumerate(raw, start=1)
        ]
        self._ids["event"] = len(self.events)

    # --- reads the endpoints share -----------------------------------------------------
    def org_of(self, user: User) -> Optional[Org]:
        return self.orgs.get(user.org_id) if user.org_id else None

    def current_assignment(self, subject_type: str, subject_id: int) -> Optional[Assignment]:
        now = self.current()
        for a in reversed(self.assignments):
            if a.subject_type == subject_type and a.subject_id == subject_id and a.status in ("active", "trial"):
                if a.ends_at is None or a.ends_at > now:
                    return a
        return None

    def default_plan(self) -> Plan:
        return next(p for p in self.plans.values() if p.is_default)

    def effective_plan(self, user: User) -> tuple[Plan, str, Optional[Assignment]]:
        """5.4.2: the person's own assignment, else their organisation's, else the default."""
        own = self.current_assignment("user", user.id)
        if own:
            return self.plans[own.plan_id], "user", own
        if user.org_id:
            org = self.current_assignment("organization", user.org_id)
            if org:
                return self.plans[org.plan_id], "organization", org
        return self.default_plan(), "default", None

    def usage_30d(self, user_id: int) -> tuple[int, Optional[float]]:
        since = self.current().date() - timedelta(days=29)
        tokens, cost, known = 0, 0, False
        for row in self._usage_by_user().get(user_id, []):
            if row.day >= since:
                tokens += row.tokens
                if row.cost_micro_usd is not None:
                    cost += row.cost_micro_usd
                    known = True
        return tokens, (round(cost / 1e6, 2) if known else None)

    def _usage_by_user(self) -> dict[int, list[UsageDay]]:
        cache = getattr(self, "_by_user_cache", None)
        if cache is None or cache[0] != len(self.usage):
            index: dict[int, list[UsageDay]] = {}
            for row in self.usage:
                if row.user_id is not None:
                    index.setdefault(row.user_id, []).append(row)
            cache = (len(self.usage), index)
            self._by_user_cache = cache
        return cache[1]

    def live_tokens(self, user_id: Optional[int] = None) -> list[Token]:
        now = self.current()
        return [
            t
            for t in self.tokens
            if not t.blacklisted
            and t.expires_at > now
            and (user_id is None or t.user_id == user_id)
            and self.users[t.user_id].status != "deleted"
        ]

    def daily_tokens(self, user_id: int, day: date) -> int:
        return sum(r.tokens for r in self._usage_by_user().get(user_id, []) if r.day == day)

    def median_daily_tokens(self, user_id: int, before: date) -> float:
        by_day: dict[date, int] = {}
        for r in self._usage_by_user().get(user_id, []):
            if before - timedelta(days=30) <= r.day < before:
                by_day[r.day] = by_day.get(r.day, 0) + r.tokens
        return float(statistics.median(by_day.values())) if by_day else 0.0
