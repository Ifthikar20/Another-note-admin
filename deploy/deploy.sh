#!/usr/bin/env bash
# Deploy, or roll back, AnotherNote Admin on this box. Lives in /opt/anothernote-admin
# with docker-compose.yml and render-env.sh (deploy-aws.sh puts them there).
#
#   sudo ./deploy.sh <git-sha>    run that version of admin-web: a commit on main that the
#                                 release workflow built, scanned and pushed to ECR. A
#                                 rollback is the same command with an earlier SHA.
#   sudo ./deploy.sh --status     what runs now, and the last deploys; changes nothing
#
# Steps: settings from SSM -> pull admin-web and cloudflared -> rebuild the admin API from
# the backend's tree -> start what changed and wait for it to be healthy -> check that no
# container publishes a port -> one line in deploys.log, and the same in CloudWatch: when,
# who, which version and image digest, and whether it worked (the change record for this
# service). The settings become .env only when all of that worked, so .env always
# describes what runs.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PROJECT=anothernote-admin
LOG=deploys.log
NEXT=.env.next

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
setting() { sed -n "s/^$1='\(.*\)'$/\1/p" "$NEXT" | tail -n 1; }
last_good() { if [ -f "$LOG" ]; then awk -F'\t' '$5 == "ok" { v = $3 } END { print v }' "$LOG"; fi; }
is_ecr() { [[ "$1" == *.dkr.ecr.*.amazonaws.com ]]; }
running() { docker ps --filter "label=com.docker.compose.project=$PROJECT" "$@"; }

[ "$(id -u)" = 0 ] || die "run it with sudo: .env and deploys.log are root's"
[ $# -eq 1 ] || die "usage: sudo $0 <git-sha> | --status"

if [ "$1" = --status ]; then
  running --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
  if [ -f "$LOG" ]; then
    printf '\nlast deploys (UTC, who, version, image, result):\n'
    tail -n 5 "$LOG"
  fi
  exit 0
fi

VERSION="$1"
[[ "$VERSION" =~ ^[0-9a-f]{40}$ ]] || die "give the full 40-character git SHA (deploy-aws.sh resolves short ones)"
PREVIOUS="$(last_good)"
DIGEST=-
DONE=0
REGION=
GROUP=
record() {
  local at by line
  at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  by="${SUDO_USER:-root}"
  printf '%s\t%s\t%s\t%s\t%s\n' "$at" "$by" "$VERSION" "$DIGEST" "$1" >> "$LOG"
  # The same record off the box, in the service's log group (stream "deploys"), once the
  # settings say where that is. None of these values can hold a quote.
  [ -n "$REGION" ] || return 0
  line="{\"event\":\"deploy\",\"result\":\"$1\",\"version\":\"$VERSION\",\"image\":\"$DIGEST\",\"by\":\"$by\",\"at\":\"$at\"}"
  aws logs create-log-stream --region "$REGION" --log-group-name "$GROUP" --log-stream-name deploys > /dev/null 2>&1 || true
  aws logs put-log-events --region "$REGION" --log-group-name "$GROUP" --log-stream-name deploys \
    --log-events "[{\"timestamp\":$(date +%s)000,\"message\":\"${line//\"/\\\"}\"}]" > /dev/null 2>&1 ||
    echo "warning: this deploy's record is only in $LOG: it could not be written to CloudWatch ($GROUP)" >&2
}
compose() { docker compose --env-file "$NEXT" -p "$PROJECT" "$@"; }
finish() {
  rm -f "$NEXT"
  if [ "$DONE" != 1 ]; then
    record failed
    echo "the deploy of $VERSION failed.${PREVIOUS:+ The last good version: sudo $0 $PREVIOUS}" >&2
  fi
}
trap finish EXIT

echo "==> settings from SSM"
ADMIN_WEB_VERSION="$VERSION" ENV_FILE="$NEXT" ./render-env.sh
IMAGE="$(setting ADMIN_WEB_IMAGE)"
REGION="$(setting AWS_REGION)"
GROUP="$(setting ADMIN_LOG_GROUP)"
GROUP="${GROUP:-/anothernote/admin}"
BACKEND_DIR="$(setting BACKEND_DIR)"
BACKEND_DIR="${BACKEND_DIR:-/opt/playstudy/backend}"
[ -f "$BACKEND_DIR/app/admin_main.py" ] ||
  die "$BACKEND_DIR has no app/admin_main.py: deploy the backend with its admin API (phase 2) first"

REGISTRY="${IMAGE%%/*}"
if is_ecr "$REGISTRY"; then
  echo "==> signing in to $REGISTRY"
  aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY" > /dev/null
fi

echo "==> pulling admin-web $VERSION and cloudflared"
compose pull --quiet admin-web cloudflared
DIGEST="$(docker image inspect -f '{{join .RepoDigests ","}}' "$IMAGE:$VERSION")"
if is_ecr "$REGISTRY"; then docker logout "$REGISTRY" > /dev/null; fi

echo "==> building the admin API from $BACKEND_DIR"
compose build --quiet admin-api

echo "==> starting, and waiting for health checks"
compose up -d --remove-orphans --wait --wait-timeout 180

published="$(running --format '{{.Names}} {{.Ports}}' | grep -e '->' || true)"
[ -z "$published" ] || die "a container publishes a port, which this project never does: $published"

mv -f "$NEXT" .env
DONE=1
record ok
echo "==> running $VERSION"
running --format 'table {{.Names}}\t{{.Status}}'
