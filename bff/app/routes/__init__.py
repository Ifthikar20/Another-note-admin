"""
Every route the admin UI uses, and nothing else (6.3.3). Each one maps to exactly one
admin API route, checks the role table itself, and forwards only what it validated.
"""

from fastapi import APIRouter

from . import activity, audit, config, events, me, orgs, overview, plans, security, tickets, usage, users

router = APIRouter()
for module in (me, overview, users, usage, tickets, events, plans, orgs, security, activity, audit, config):
    router.include_router(module.router)
