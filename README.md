# AnotherNote Admin

AnotherNote's internal admin console (build specification, section 6): who uses the
product and how, what it costs, support tickets, sign-in security, what students did and
what went wrong for them, plans, organisations, and the audit log. Staff see counts and
metadata, masked identities, and never a student's content.

One image: a React single-page app and the FastAPI BFF that serves it. The BFF checks the
Cloudflare Access sign-in and the member list on every request, then calls the internal
admin API of playstudy-backend (phase 2), signing each call with the member's email and
role, and passes back only the fields [`bff/app/contract.py`](bff/app/contract.py) names.
It holds no database credentials.

## Run it on your machine

Python 3.11 or later, and Node 22.

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
(cd web && npm ci)
python scripts/dev.py --web                        # then open http://127.0.0.1:8080
```

That starts a stand-in admin API with made-up data (`devstub/`, on 127.0.0.1:8001), the
BFF (8090) and Vite (8080), all bound to this machine only, signed in as
`dev@localhost` with the owner role. `--role support` (or `analyst`, `viewer`) shows the
app as that role; `--no-stub --admin-api http://127.0.0.1:8001` uses the real admin API
from playstudy-backend instead. The development identity works only with
`ENVIRONMENT=development` on a server bound to 127.0.0.1: the BFF refuses to start
otherwise.

The real image, locally: `docker compose -f docker-compose.dev.yml --profile stub up --build`,
then http://127.0.0.1:8090.

## Tests

```bash
pytest                                      # the BFF and the stand-in
ruff check . && ruff format --check .
cd web
npm run lint && npm run typecheck && npm test
npm run build && npm run e2e                # Playwright: the production build, served by the BFF
```

CI runs all of that on every pull request, plus the image scan, its bill of materials,
dependency audits and a secret scan ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Where things are

```
bff/app/            the BFF
  main.py             the app: static files, /bff routes, error handling
  guard.py            every request: Access token, member list, CSRF checks, headers, logs
  access.py           Cloudflare Access token verification
  members.py          ADMIN_MEMBERS, roles and what each may do
  signing.py          the HMAC signature on admin API calls
  admin_client.py     the one client of the admin API
  contract.py         every admin API answer, field by field; shape.py enforces it
  logs.py             log format and request ids
  routes/             one module per page area, each route an explicit mapping
bff/tests/          its tests
devstub/            the stand-in admin API, for development and tests only
web/src/            the SPA: pages/, components/, lib/ (API client, formatting)
web/e2e/            the Playwright suite
deploy/             production: the compose project and the deploy scripts
docs/               deploying, SOC 2, runbooks, the admin API contract
scripts/dev.py      the local runner
```

## Settings

The BFF reads its environment (in production, from SSM: [docs/DEPLOY.md](docs/DEPLOY.md)).

| Variable | |
|---|---|
| `ENVIRONMENT` | `production` (the default) or `development` |
| `ADMIN_API_URL` | the admin API's origin, e.g. `http://admin-api:8001` |
| `ADMIN_SERVICE_TOKEN`, `ADMIN_SIGNING_KEY` | shared with the admin API; two different values of 32 characters or more |
| `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD` | the Cloudflare Access team domain and application AUD tag (required in production) |
| `ADMIN_MEMBERS` | `email:role` pairs, comma separated; roles `owner`, `support`, `analyst`, `viewer` |
| `ADMIN_PUBLIC_ORIGIN` | the public origin, for the same-origin check on changes (`https://admin.anothernote.app`) |
| `ADMIN_IDLE_LOCK_MINUTES`, `ADMIN_IDLE_SIGNOUT_MINUTES` | idle lock and sign-out (15 and 60) |
| `ADMIN_DEV_IDENTITY` | development only: `email:role` |
| `ADMIN_BIND_HOST`, `ADMIN_PORT` | where `python -m bff.app` listens (127.0.0.1:8090; the image uses 0.0.0.0:8080) |
| `LOG_FORMAT`, `LOG_LEVEL` | `text` or `json` (the image uses `json`); `INFO` |

## More

- [docs/DEPLOY.md](docs/DEPLOY.md): the one-time setup (database role, SSM, ECR,
  Cloudflare Tunnel and Access, logs), releasing, deploying, checking, rolling back.
- [docs/RUNBOOKS.md](docs/RUNBOOKS.md): adding and removing members, the access review,
  rotating secrets, incidents.
- [docs/SOC2.md](docs/SOC2.md): which SOC 2 criteria this covers, the evidence to keep,
  and what the company must do besides.
- [docs/ADMIN_API_CONTRACT.md](docs/ADMIN_API_CONTRACT.md): for playstudy-backend's phase
  2: signing, errors, every call the BFF makes, and the JSON Schema of the answers.
- [SECURITY.md](SECURITY.md): reporting a vulnerability.

To check the signing test vector (`bff/tests/test_signing.py`) with openssl:

```bash
body='{"reason":"Replying to their ticket AN-0042","ticket_id":42}'
printf 'POST\n/admin/v1/users/481/reveal-email\n1790516426\njane@anothernote.app\nsupport\n1f0c2d9e-8b1a-4c3e-9f5d-2a7b6c4d8e10\n%s' \
  "$(printf '%s' "$body" | openssl dgst -sha256 -r | cut -d' ' -f1)" |
  openssl dgst -sha256 -binary -hmac 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef |
  openssl base64 -A | tr '+/' '-_' | tr -d '='
# 3BMWI3AhFmatma_RJTeyPUMcgBL8V7t1loE-08dQ-0c
```

## Status

Phase 3 of the build specification: complete, and tested against the stand-in. Before it
can serve staff, playstudy-backend needs phases 1 and 2 (usage metering, sign-in events,
plans, tickets v2, the audit log, the views and role of Appendix A, and the admin API).
Phase 4 is [docs/DEPLOY.md](docs/DEPLOY.md).
