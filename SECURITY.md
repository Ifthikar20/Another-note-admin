# Security

This is AnotherNote's internal admin console. It shows metadata about student accounts,
never their content, and only to staff signed in through Cloudflare Access.

## Reporting a vulnerability

Do not open an issue or a pull request that describes it. Tell the repository owner
directly (or use GitHub's private vulnerability reporting, when it is on for this
repository), with what you found and how to reproduce it. You will get an answer within
two working days. What happens next is in [docs/RUNBOOKS.md](docs/RUNBOOKS.md), "A security
incident".

## How the app protects what it shows

[docs/SOC2.md](docs/SOC2.md) lists each control, where it lives in the code, and what the
company must do alongside it. In short:

- Sign-in: Cloudflare Access (single sign-on and multi-factor) in front, the Access token
  verified again by the BFF on every request, and a member list with four roles.
- No database credentials in this app: it calls one private admin API, signing each call
  with the member's email and role, and shows only the fields `bff/app/contract.py` names.
- Every admin action is written to the audit log by the admin API.
- The image is distroless, runs as a non-root user on a read-only filesystem, publishes
  no port, and is scanned for known vulnerabilities before it is released.

## Supported versions

Only what runs in production (the latest release from `main`) receives fixes.
