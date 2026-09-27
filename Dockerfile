# syntax=docker/dockerfile:1
# AnotherNote Admin: the SPA and its BFF in one image (build specification 6.1).
#
#   docker build -t anothernote-admin:$(git rev-parse --short HEAD) .
#
# Behind a proxy that inspects TLS, hand the build its CA bundle as a secret (it is used
# for npm and pip only, and is never stored in a layer):
#   docker build --secret id=extra_ca,src=/path/to/ca-bundle.pem ...
#
# Three stages: Node builds the SPA; Python installs the BFF's pinned dependencies; the
# final image is distroless: Python and the app, no shell, no package manager, no build
# tools. It runs as a non-root user and needs no writable filesystem (run it with
# read_only: true). Nothing from devstub/, the tests or the docs is in it.
#
# Base images are pinned by digest, so a build is repeatable and a new base is a reviewed
# change (Dependabot proposes them). The runtime is Debian 13's Python 3.13, not the 3.11
# of build specification 6.1: distroless's Debian 12 image trails Debian's security fixes
# (in September 2026 it still had OpenSSL 3.0.19 and CVEs fixed upstream), which the image
# scan in CI rightly refuses. CI runs the tests on 3.11 and 3.13.

# --- 1. the SPA ---------------------------------------------------------------------------
FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- 2. the BFF's dependencies ---------------------------------------------------------
FROM python:3.13-slim-trixie@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b AS deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY bff/requirements.txt /tmp/requirements.txt
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-compile --target /deps -r /tmp/requirements.txt
COPY bff/__init__.py /app/bff/__init__.py
COPY bff/app /app/bff/app
# Compiled ahead of time: the running container cannot (and need not) write .pyc files.
RUN python -m compileall -q /deps /app/bff

# --- 3. what runs ----------------------------------------------------------------------
# Debian 13's Python 3.13, the same minor version the dependencies were installed for.
FROM gcr.io/distroless/python3-debian13:nonroot@sha256:8ee214843129f43e2ebf5e0ca9f2e4e6d8292143d1b8a6787f169b5898578884
COPY --from=deps /deps /app/deps
COPY --from=deps /app/bff /app/bff
COPY --from=web /web/dist /app/static
WORKDIR /app
ENV PYTHONPATH=/app/deps:/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ADMIN_STATIC_DIR=/app/static \
    ADMIN_BIND_HOST=0.0.0.0 \
    ADMIN_PORT=8080 \
    ENVIRONMENT=production \
    LOG_FORMAT=json
USER nonroot
EXPOSE 8080
# Liveness only: /healthz answers {"ok": true} without identity and says nothing else.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["/usr/bin/python3", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('ADMIN_PORT', '8080'), timeout=4)"]
ENTRYPOINT ["/usr/bin/python3", "-m", "bff.app"]
