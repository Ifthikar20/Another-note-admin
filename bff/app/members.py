"""
Who may use the admin app, and what each role may do.

ADMIN_MEMBERS lists the staff as `email:role` pairs, comma separated. Cloudflare Access
decides who reaches the app at all; this list decides who is let in once they have. Both
must agree: a person Cloudflare lets through but who is not listed here gets a 403.

The capability table is section 5.8.3 of the build specification, split where the
endpoint table (5.8.4) is stricter than it (a person's tickets and the live ticket events
are support+, though viewers may read the inbox). The admin API enforces the same table;
this copy lets the BFF refuse early and lets the UI hide what a role cannot do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ROLES = ("owner", "support", "analyst", "viewer")

_ALL = frozenset(ROLES)
_OWNER = frozenset({"owner"})
_SUPPORT_UP = frozenset({"owner", "support"})

CAPABILITIES: dict[str, frozenset[str]] = {
    # Overview, metrics, usage and cost
    "metrics.read": _ALL,
    # User list and detail (masked), a person's live sessions and plan
    "users.read": _ALL,
    "users.reveal_email": _SUPPORT_UP,
    "users.sign_out": _SUPPORT_UP,
    "users.set_active": _OWNER,
    # One person's sign-in and security events
    "users.auth_events": _SUPPORT_UP,
    # One person's tickets (5.8.4: support+)
    "users.tickets": _SUPPORT_UP,
    # The ticket inbox
    "tickets.read": frozenset({"owner", "support", "viewer"}),
    "tickets.write": _SUPPORT_UP,
    # The live stream of new tickets and replies (5.8.4: support+)
    "tickets.events": _SUPPORT_UP,
    "plans.read": _ALL,
    "plans.write": _OWNER,
    "orgs.read": _ALL,
    "security.read": _SUPPORT_UP,
    # What people did in the app, event by event, with who did it (a behavioural trail:
    # support+). The grouped views (Activity overview, What went wrong) are metrics.read.
    "activity.read": _SUPPORT_UP,
    "audit.read": _OWNER,
    # Settings: admin members and the price table in force
    "settings.read": _OWNER,
}

# One @, no spaces, no separators of the ADMIN_MEMBERS list itself. Loose on purpose:
# the identity provider has already decided what an email address is; this only keeps
# a typo in the list from silently matching nobody. ASCII only, so it can travel in a
# header to the admin API.
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+")


class MembersError(ValueError):
    """ADMIN_MEMBERS (or ADMIN_DEV_IDENTITY) is not a list of email:role pairs."""


@dataclass(frozen=True)
class Member:
    """A signed-in staff member: the actor of every admin request."""

    email: str
    role: str

    def can(self, capability: str) -> bool:
        return self.role in CAPABILITIES[capability]

    @property
    def capabilities(self) -> list[str]:
        return sorted(c for c, roles in CAPABILITIES.items() if self.role in roles)


def parse_pair(raw: str) -> Member:
    """One `email:role` pair, e.g. `jane@anothernote.app:support`."""
    email, sep, role = raw.strip().rpartition(":")
    email, role = email.strip().lower(), role.strip().lower()
    if not sep or not _EMAIL.fullmatch(email):
        raise MembersError(f"not an email:role pair: {raw.strip()!r}")
    if role not in ROLES:
        raise MembersError(f"unknown role {role!r} for {email} (roles: {', '.join(ROLES)})")
    return Member(email=email, role=role)


def parse_members(raw: str) -> dict[str, str]:
    """ADMIN_MEMBERS as {email: role}. Every entry must parse; an email may appear once."""
    members: dict[str, str] = {}
    for part in (raw or "").split(","):
        if not part.strip():
            continue
        member = parse_pair(part)
        if member.email in members:
            raise MembersError(f"{member.email} is listed more than once")
        members[member.email] = member.role
    return members
