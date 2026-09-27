# SOC 2 and the admin console

## What SOC 2 is, and what code can do about it

A SOC 2 report is an independent CPA firm's opinion on whether AnotherNote's controls meet
the AICPA Trust Services Criteria. A **Type I** report says they are designed properly on
one date; a **Type II** report says they also worked throughout a period, usually three to
twelve months. Schools and districts that ask for SOC 2 almost always mean Type II.

The report covers the company and the whole system in scope: the student app, the
backend, AWS, Cloudflare, GitHub, Google Workspace, the people, and the written policies.
No repository makes a company compliant. What this one does is implement the technical
controls around the most sensitive thing an auditor will look at in a product like
AnotherNote, staff access to student data, and produce the evidence those controls
worked. The rest is in "What the company must do" below.

SOC 2 is also not a privacy law. AnotherNote has students under 13 and school customers,
so COPPA, FERPA and state student-privacy laws apply whatever the report says; take
counsel on them separately.

## The path to a report

1. **Scope**: the AnotherNote product and the infrastructure it runs on. Criteria:
   Security (required) and Confidentiality; Availability and Privacy can come later.
2. **Policies**, written, approved by leadership, read by staff, reviewed yearly:
   information security, access control, change management, vulnerability management,
   logging and monitoring, incident response, business continuity and backups, data
   classification, retention and disposal, encryption, vendor management, risk
   assessment, acceptable use, and HR security (hiring, training, leaving).
3. **Close the gaps** listed below.
4. **Readiness assessment** by the audit firm or a consultant; fix what it finds.
5. **Type I** report.
6. **Observation period**: run every control, and keep the evidence as you go (the
   calendar below). Three to six months is usual for a first Type II.
7. **Type II** report, then one a year.

A compliance platform (Vanta, Drata, Secureframe and others) connects to AWS, GitHub,
Google Workspace and Cloudflare, collects much of the evidence itself, and supplies policy
templates; for a small team it usually pays for itself.

## Controls in this repository

| Criteria | Control | Where | Evidence to keep |
|---|---|---|---|
| CC6.1 | Staff sign in through Cloudflare Access with single sign-on and a second factor; nothing is reachable without it | Cloudflare (docs/DEPLOY.md, step 7) | The Access application and policy settings; Access logs |
| CC6.1 | The BFF verifies the Access token again on every request, static files included: RS256, audience, issuer, expiry, keys cached for an hour | `bff/app/access.py`, `bff/app/guard.py`; tests in `bff/tests/test_access.py` | CI runs |
| CC6.1, CC6.3 | Four roles with a capability table; every route checks it, and the admin API checks its own; the database role reads views only | `bff/app/members.py`, `bff/app/deps.py`; the role-by-role test in `bff/tests/test_routes.py`; the backend's Appendix A grants | `ADMIN_MEMBERS` history in SSM; CI runs |
| CC6.1, C1.1 | Least exposure: identities masked everywhere; revealing an email needs a reason, is audited, and masks again after 60 seconds, held in the page's memory only | `web/src/components/RevealEmail.tsx`; the admin API's `admin_reveal_email()` | Audit rows `user.reveal_email` |
| CC6.1 | Sessions: the screen locks after 15 idle minutes and drops what it showed; after 60 it signs out of Access; an Access session lasts 8 hours | `web/src/components/IdleLock.tsx`, `ADMIN_IDLE_*` | Settings; the e2e test "the screen locks when idle" |
| CC6.2 | One list of members (SSM), matching the Access policy; an access review page with a CSV of each member's role and last action | `bff/app/routes/config.py`, Settings > Access review | The quarterly review, signed (see the calendar) |
| CC6.6 | No inbound port: Cloudflare Tunnel only; internal networks; the admin API listens on the internal network alone; a deploy fails if anything publishes a port | `deploy/docker-compose.yml`, `deploy/deploy.sh` | The compose file at each release; the security group rules; an outside port scan, yearly |
| CC6.6, CC6.7 | Browser protections: Content-Security-Policy with no inline script, frame denial, no referrer, HSTS, no-store on every data response; cross-site requests refused | `bff/app/guard.py`; `bff/tests/test_guard.py`; the CI check for inline scripts | CI runs |
| CC6.7, C1.1 | Nothing leaves that the contract does not name: the BFF prunes every admin API answer to an allow-list, tested with a deliberately leaky admin API; no third-party script, font or call; the only export is the audit log, with spreadsheet formulas neutralised | `bff/app/contract.py`, `bff/app/shape.py`, `bff/tests/test_shape.py`, `bff/app/routes/audit.py` | CI runs |
| CC6.1, CC6.7 | Secrets only in SSM (encrypted), read by the box's role at deploy time; no secret in git, in images or on laptops; a secret scan over the whole history on every change | `deploy/render-env.sh`; the `secrets` CI job, `.gitleaksignore` | SSM parameter history; CI runs |
| CC6.8 | A minimal, hardened image: distroless, non-root, read-only, no shell, capabilities dropped; base images pinned by digest | `Dockerfile`, `deploy/docker-compose.yml` | The Dockerfile at each release |
| CC7.1 | Known vulnerabilities: image scan (Trivy), `pip-audit` and `npm audit` on every change and before every release; Dependabot weekly; ECR scans on push | `.github/workflows/ci.yml`, `.github/dependabot.yml` | CI runs; Dependabot pull requests; triage records (below) |
| CC7.2 | Monitoring: one JSON log line per request (member, role, route, status, request id; never a query or a body) and a warning for every refusal, kept 400 days in CloudWatch, with alarms; the audit log of every admin request in the database, kept a year | `bff/app/logs.py`, `bff/app/guard.py`; docs/DEPLOY.md, "Operate"; the admin API (build specification 5.6) | Retention settings; alarm definitions; alarm notifications and what was done about each |
| CC7.2, CC7.3 | Tracing: every request's id is on its log line, in the audit row, and on the error message staff see ("Reference 1f0c2d9e") | `bff/app/logs.py`, `web/src/lib/api.ts`; docs/ADMIN_API_CONTRACT.md | Incident records that use it |
| CC7.3 to CC7.5 | Response: runbooks for a security incident, a compromised account, removing access, rotating secrets | [RUNBOOKS.md](RUNBOOKS.md) | Incident records; post-incident reviews; a yearly tabletop exercise |
| CC8.1 | Change management: every change by pull request, reviewed by a code owner, with a privacy and security checklist; required CI checks; releases only from `main` after every check; deploys only of commits on `main`; immutable image tags; every deploy recorded with its image digest; rollback by SHA | `.github/`, `deploy/deploy-aws.sh`, `deploy/deploy.sh` | Pull request history; the branch protection settings; CI and release runs; the `deploys` log stream |
| CC9.2 | A software bill of materials for every image | The `image` CI job (SPDX artifact) | The SBOMs, kept 90 days by GitHub: copy the release ones to the evidence folder |
| C1.1, C1.2 | Data minimisation by design: the admin app shows counts and metadata, never a student's content; the Activity area shows page paths, action names and error messages only | Build specification section 3; `bff/app/contract.py` | The canary test; section 3 in the evidence folder |
| A1.2 | Health checks, automatic restarts, a deploy that waits for health, rollback by SHA | `Dockerfile`, `deploy/` | `deploys` stream |

## What the company must do

What an auditor will ask about that no code here can answer.

**People and governance** (CC1, CC2): a named security owner; policies as above, with
staff acknowledgements; security training at hiring and yearly; background checks where
lawful; confidentiality agreements; onboarding and offboarding checklists (offboarding
removes admin access the same day: [RUNBOOKS.md](RUNBOOKS.md)); a second person to review
changes, since an author cannot approve their own pull request.

**Risk and vendors** (CC3, CC9): a yearly risk assessment and a risk register; a vendor
list with each vendor's SOC 2 report reviewed yearly: AWS, Cloudflare, GitHub, Google
Workspace, and the AI providers the backend sends student content to (Anthropic,
DeepSeek, Perplexity, ElevenLabs, Speechify), each with a data processing agreement that
rules out training on that content.

**AWS**: CloudTrail in every region, to a locked bucket, with log file validation;
GuardDuty; multi-factor on the root account and no root access keys; every person signs
in as themselves (IAM Identity Center) with multi-factor, and no shared keys; encrypted
EBS volumes. The box accepts SSH from the internet with one shared key
(`playstudy-turnstile.pem`, used by the backend and web deploys): move shell access and
deploys to SSM Session Manager, close port 22, and give each person their own access.

**Data**: the production database is a Docker volume on one instance, with no backup this
repository can see. Back it up (nightly, encrypted, to another account or region), and
test a restore every quarter. Implement the retention decided in build specification
section 9 (90 days of usage events, 180 of sign-in events, a year of audit log) and the
purge job for deleted accounts (phase 5).

**Identity provider**: 2-Step Verification enforced in Google Workspace for everyone;
few admins; leaving staff suspended at once (which also ends their Access sign-in; revoke
their Access session for immediate effect).

**Cloudflare**: multi-factor on the Cloudflare account and few administrators; keep the
Access logs (the free plan keeps them briefly: export them monthly, or use Logpush on a
paid plan).

**GitHub**: two-factor sign-in for everyone with access; branch protection as in
[DEPLOY.md](DEPLOY.md), step 8; a quarterly look at who has access.

**Laptops**: disk encryption, screen lock, automatic updates; a device management tool
makes this provable.

**The rest of the product**: the same practices in playstudy-backend and
playstudy-card-dash (reviews, CI, scans, pinned dependencies), a penetration test once a
year, and a way for outsiders to report vulnerabilities.

## Evidence calendar

| When | What | Kept in |
|---|---|---|
| Every change | Pull request with approval, green CI, release run, deploy record | GitHub, ECR, CloudWatch (`deploys`) |
| Continuously | Request logs, refusals, alarms; the audit log | CloudWatch; the database |
| Weekly | Dependabot pull requests reviewed and merged or declined with a reason | GitHub |
| Monthly | Vulnerability triage records; Cloudflare Access logs exported | The evidence folder |
| Quarterly | Access review: the Access review CSV compared with the Access policy, Google Workspace, GitHub and AWS, then signed and dated; a database restore test | The evidence folder |
| Yearly | Policies reviewed; risk assessment; vendor reviews; penetration test; incident tabletop; security training; secrets rotated | The evidence folder |

## Triage records

A finding the checks do not fail on still gets a decision, written down. For example:

> **2026-09-27, react-router 6.30 (moderate)**: two advisories. An open redirect through a
> crafted `<Link>` or `navigate()` target: this app builds link targets from numeric ids
> and its own routes, never from input, so it is not reachable. Constructor injection in
> server-side hydration: this app does not render on the server. Fixed only in version 7,
> a major upgrade: scheduled as a normal change; revisit by 2026-12-31. Decided by: the
> owner.

Each record names the advisory, what it affects, whether it can be exploited here and why,
the decision, who made it, and a date to look again.
