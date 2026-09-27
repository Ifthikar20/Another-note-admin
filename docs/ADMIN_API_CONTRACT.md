# The admin API contract

For whoever builds phase 2 in playstudy-backend (build specification 5.7 and 5.8): what
this app sends to the internal admin API, and what it accepts back. The admin app is the
admin API's only client.

Sources of truth, in this repository:

| What | Where |
|---|---|
| Every answer, field by field | [`bff/app/contract.py`](../bff/app/contract.py), and as JSON Schema in [`admin-api.schema.json`](admin-api.schema.json) |
| Signing | [`bff/app/signing.py`](../bff/app/signing.py) |
| A working admin API that honours all of this, with made-up data | [`devstub/app.py`](../devstub/app.py) (`python scripts/dev.py` runs it) |

The table below and the schema file are generated from the code, and a test fails when
they are out of date, so they can be trusted. Validating the real admin API's answers
against `admin-api.schema.json` in the backend's own tests is the cheapest way to keep the
two repositories in step.

## What the BFF does with an answer

It keeps only the fields `contract.py` names and drops the rest, with a log line naming
each dropped path (never its value). A field of the wrong type is dropped too. Free-form
maps (usage by feature, error counts by kind) keep only keys and string values that look
like identifiers. So a field the admin API adds by mistake never reaches a screen, and a
field this contract needs but the admin API leaves out shows as "—". That is a backstop,
not a licence: section 3 of the specification (what the admin app may and may not show)
binds the admin API first.

## Authentication (5.8.2)

Every call carries:

```
Authorization:      Bearer <ADMIN_SERVICE_TOKEN>
X-Admin-Actor:      jane@anothernote.app          (lower case)
X-Admin-Role:       support                       (owner, support, analyst or viewer)
X-Admin-Request-Id: 1f0c2d9e-8b1a-4c3e-9f5d-2a7b6c4d8e10   (uuid4)
X-Admin-Timestamp:  1790516426                    (unix seconds)
X-Admin-Signature:  base64url(HMAC-SHA256(key, message)), no padding
```

The message is seven lines joined by a single `\n`, with no newline at the end:

1. the method, upper case;
2. the request target exactly as it arrives: path and query, no host. The BFF
   percent-encodes every query key and value with no safe characters (`@` is `%40`, a
   space is `%20`), leaves out empty values, and keeps its own order. Check the raw
   target as received (`scope["raw_path"]` plus `?` plus `scope["query_string"]` in
   ASGI), never a re-encoded one;
3. the timestamp as sent;
4. the actor, 5. the role and 6. the request id, as sent;
7. the SHA-256 of the body bytes in lower-case hex (for no body, that of the empty
   string: `e3b0c442…b855`).

The key is `ADMIN_SIGNING_KEY` as UTF-8 text, not hex-decoded.

A test vector (it is in `bff/tests/test_signing.py`, and `openssl` agrees):

```
key        0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
message    POST
           /admin/v1/users/481/reveal-email
           1790516426
           jane@anothernote.app
           support
           1f0c2d9e-8b1a-4c3e-9f5d-2a7b6c4d8e10
           <sha256 of {"reason":"Replying to their ticket AN-0042","ticket_id":42}>
signature  3BMWI3AhFmatma_RJTeyPUMcgBL8V7t1loE-08dQ-0c
```

The admin API refuses with 401 when the token is wrong (compare in constant time), the
timestamp is more than 60 seconds off, the signature is wrong, or the request id was seen
in the last 5 minutes (`SET admin:rid:<id> NX EX 300`). It refuses with 403 when the role
may not use the route: it enforces the role table itself, whatever the BFF allowed.

The BFF retries a call once, and only when the connection could not be made (the request
never arrived), with the same request id.

### The request id is also the trace id

Every staff request to the BFF gets an id. The BFF returns it as `X-Request-Id`, puts it
on its log line, and sends it as `X-Admin-Request-Id` on the first admin API call it
makes for that request (later calls of the same request get fresh ids, listed on the same
log line). **Store `X-Admin-Request-Id` in the audit row's `request_id`**, and put it on
the admin API's own log lines: then an audit row, a BFF log line, an admin API log line
and the "Reference 1f0c2d9e" a staff member reads off an error message all lead to each
other.

## Errors (5.8.5)

`{"error": {"code": "...", "message": "..."}}` with the matching status. What staff see:

| Admin API answers | The BFF answers | Message shown |
|---|---|---|
| 400 or 422 | 400 `invalid` | the admin API's message (so make it a sentence for people) |
| 401 | 502 `unavailable` | "The admin API refused this app's credentials. Tell the owner." (and an error in the log: token, key or clock) |
| 403 | 403 `forbidden` | the admin API's message |
| 404 | 404 `not_found` | the admin API's message |
| 409 | 409 `conflict` | the admin API's message |
| 429 | 429 `unavailable` | a fixed message |
| 5xx, or not JSON | 502 `unavailable` | a fixed message: a 5xx message is never passed on, as it could hold a database error |

Messages are cut to 300 characters, with control characters removed. Never echo input
back in a message: an exact-email search must not come back in an error.

## Lists

Cursor pagination as in 5.8.4: `?cursor=` (opaque) and `limit` (up to 100); answers are
`{"items": [...], "next_cursor": "..." | null}`. Times are ISO 8601 in UTC. Days are UTC
days (`2026-10-31`), and ranges are `from` and `to`, both included.

## Live events

`GET /admin/v1/events/stream?after=<id>` answers `text/event-stream`. Each event has
`id:` (the outbox id), `event:` (`ticket.created` or `ticket.user_replied`) and `data:`
(one JSON `OutboxEvent`: `id`, `kind`, `ticket_id`, `created_at`, and nothing else: no
message text). Send a comment line (`: ping`) at least every 30 seconds: the BFF gives up
on a stream that is silent for 90. `GET /admin/v1/events?after=<id>&limit=` returns the
same events as a list, oldest first, for catching up after a reconnect. The BFF passes on
only those two kinds and those four fields.

## Beyond the specification

What this app needs that 5.8.4 and Appendix B do not spell out:

- **User rows** (`UserRow`) carry `status` (`active`, `deactivated`, `deleted`) and
  `open_tickets`.
- **A person's page** (`UserDetail`) has a `profile` block (first name, kind, age band,
  organisation, plan, created, last sign-in, last seen, status) and `activity_30d` (active
  minutes per UTC day), besides `footprint`, `family`, `security` and
  `usage_by_feature_30d`. `footprint` is counts and bytes only.
- **Ticket lists** (`TicketList`) carry `counts` per queue, for the queue tabs.
- **Usage summaries** (`UsageSummary`) carry `month_to_date`: this month's cost and the
  monthly budget the owner set, for the budget meter.
- **`GET /admin/v1/usage/prices`**: the price table in force (Settings page, owner).
- **`GET /admin/v1/audit`** takes `exclude`, a comma-separated list of actions to leave
  out (the Audit page hides `view.*` rows by default), and `actor` for one member's rows
  (the access review reads each member's last action this way).
- **The Activity area**, from the backend's existing `analytics_events` table
  (`app/models/analytics_event.py`):
  - `GET /admin/v1/analytics/summary?from&to`: totals, events per UTC day, top pages, top
    actions, and campaigns (`utm_*` tags);
  - `GET /admin/v1/analytics/errors?from&to&q&cursor`: `kind = "error"` events grouped by
    `name`, with counts, distinct users, first and last seen, up to five paths, and a
    per-day series;
  - `GET /admin/v1/analytics/events?kind&user_id&name&path&from&to&cursor`: single events.
    Never send `data`, `client_id`, `visit_id` or `user_agent`: the contract has no place
    for them, and `data` can hold anything the browser sent.

## Every call the BFF makes

"Roles that can cause it" is what the BFF lets through; the admin API must still check
its own table (5.8.3). "The BFF sends" lists query parameters for reads and body fields
for changes; any of them may be absent.

<!-- generated by python -m bff.tests.contract_doc: do not edit by hand -->
| Admin API call | The BFF sends | Answer (`contract.py`) | Roles that can cause it | For |
|---|---|---|---|---|
| `GET /admin/v1/analytics/errors` | `cursor`, `from`, `limit`, `q`, `to` | `ErrorGroups` | every role | `GET /bff/analytics/errors` |
| `GET /admin/v1/analytics/events` | `cursor`, `from`, `kind`, `limit`, `name`, `path`, `to`, `user_id` | `AnalyticsEventList` | owner, support | `GET /bff/analytics/events` |
| `GET /admin/v1/analytics/summary` | `from`, `to` | `AnalyticsSummary` | every role | `GET /bff/analytics/summary` |
| `GET /admin/v1/audit` | `action`, `actor`, `cursor`, `exclude`, `from`, `limit`, `to` | `AuditList` | owner | `GET /bff/audit`<br>`GET /bff/audit/export.csv`<br>`GET /bff/settings/access-review`<br>`GET /bff/settings/access-review.csv` |
| `GET /admin/v1/events` | `after`, `limit` | `EventList` | owner, support | `GET /bff/events` |
| `GET /admin/v1/events/stream` | `after` | server-sent events of `OutboxEvent` | owner, support | `GET /bff/events/stream` |
| `GET /admin/v1/health` | nothing | `Health` | every role | `GET /bff/health` |
| `GET /admin/v1/metrics/active-users` | `from`, `granularity`, `to` | `ActiveUsers` | every role | `GET /bff/metrics/active-users` |
| `GET /admin/v1/metrics/online-now` | nothing | `OnlineNow` | every role | `GET /bff/metrics/online-now` |
| `GET /admin/v1/metrics/sign-ins` | `from`, `group`, `to` | `SignIns` | every role | `GET /bff/metrics/sign-ins` |
| `GET /admin/v1/orgs` | `cursor`, `limit`, `q` | `OrgList` | every role | `GET /bff/orgs` |
| `GET /admin/v1/orgs/{id}` | nothing | `OrgDetail` | every role | `GET /bff/orgs/{org_id}` |
| `PUT /admin/v1/orgs/{id}/plan` | `ends_at`, `note`, `plan_id`, `status` | `Assignment` | owner | `PUT /bff/orgs/{org_id}/plan` |
| `GET /admin/v1/overview` | `from`, `to` | `Overview` | every role | `GET /bff/overview` |
| `GET /admin/v1/plans` | nothing | `PlanList` | every role | `GET /bff/plans` |
| `POST /admin/v1/plans` | `currency`, `description`, `id`, `interval`, `is_active`, `is_default`, `limits`, `name`, `price_cents` | `Plan` | owner | `POST /bff/plans` |
| `PATCH /admin/v1/plans/{plan_id}` | `currency`, `description`, `interval`, `is_active`, `is_default`, `limits`, `name`, `price_cents` | `Plan` | owner | `PATCH /bff/plans/{plan_id}` |
| `GET /admin/v1/security/auth-events` | `cursor`, `from`, `kind`, `limit`, `to` | `AuthEventList` | owner, support | `GET /bff/security/auth-events` |
| `GET /admin/v1/security/summary` | `from`, `to` | `SecuritySummary` | owner, support | `GET /bff/security/summary` |
| `GET /admin/v1/tickets` | `assignee`, `cursor`, `limit`, `priority`, `q`, `reason`, `status` | `TicketList` | owner, support, viewer | `GET /bff/tickets` |
| `GET /admin/v1/tickets/{id}` | nothing | `TicketDetail` | owner, support, viewer | `GET /bff/tickets/{ticket_id}` |
| `PATCH /admin/v1/tickets/{id}` | `assignee_email`, `priority`, `status`, `tags` | `TicketRow` | owner, support | `PATCH /bff/tickets/{ticket_id}` |
| `POST /admin/v1/tickets/{id}/messages` | `body`, `internal` | `TicketMessage` | owner, support | `POST /bff/tickets/{ticket_id}/messages` |
| `GET /admin/v1/usage/anomalies` | `date` | `Anomalies` | every role | `GET /bff/usage/anomalies` |
| `GET /admin/v1/usage/prices` | nothing | `Prices` | owner | `GET /bff/settings/prices` |
| `GET /admin/v1/usage/summary` | `from`, `group`, `to` | `UsageSummary` | every role | `GET /bff/usage/summary` |
| `GET /admin/v1/usage/top-users` | `from`, `limit`, `metric`, `to` | `TopUsers` | every role | `GET /bff/usage/top-users` |
| `GET /admin/v1/users` | `active`, `cursor`, `kind`, `limit`, `org`, `plan`, `q`, `role`, `sort`, `status` | `UserList` | every role | `GET /bff/users` |
| `GET /admin/v1/users/{id}` | nothing | `UserDetail` | every role | `GET /bff/users/{user_id}` |
| `GET /admin/v1/users/{id}/auth-events` | `cursor`, `limit` | `AuthEventList` | owner, support | `GET /bff/users/{user_id}/auth-events` |
| `POST /admin/v1/users/{id}/deactivate` | `reason` | `ActiveResult` | owner | `POST /bff/users/{user_id}/deactivate` |
| `GET /admin/v1/users/{id}/plan` | nothing | `SubjectPlan` | every role | `GET /bff/users/{user_id}/plan` |
| `PUT /admin/v1/users/{id}/plan` | `ends_at`, `note`, `plan_id`, `status` | `Assignment` | owner | `PUT /bff/users/{user_id}/plan` |
| `POST /admin/v1/users/{id}/reactivate` | `reason` | `ActiveResult` | owner | `POST /bff/users/{user_id}/reactivate` |
| `POST /admin/v1/users/{id}/reveal-email` | `reason`, `ticket_id` | `RevealedEmail` | owner, support | `POST /bff/users/{user_id}/reveal-email` |
| `GET /admin/v1/users/{id}/sessions` | nothing | `SessionList` | every role | `GET /bff/users/{user_id}/sessions` |
| `POST /admin/v1/users/{id}/sign-out-everywhere` | `reason` | `SignOutResult` | owner, support | `POST /bff/users/{user_id}/sign-out-everywhere` |
| `GET /admin/v1/users/{id}/tickets` | `cursor`, `limit` | `TicketList` | owner, support | `GET /bff/users/{user_id}/tickets` |
| `GET /admin/v1/users/{id}/usage` | `from`, `group`, `to` | `UsageSummary` | every role | `GET /bff/users/{user_id}/usage` |
<!-- end of the generated table -->
