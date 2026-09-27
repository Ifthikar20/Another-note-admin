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

# --- 1. the SPA ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- 2. the BFF's dependencies ---------------------------------------------------------
FROM python:3.11-slim-bookworm AS deps
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
# Debian 12's Python 3.11, the same minor version the dependencies were installed for.
FROM gcr.io/distroless/python3-debian12:nonroot
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
