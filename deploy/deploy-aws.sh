#!/usr/bin/env bash
# deploy-aws.sh: ship AnotherNote Admin to the AnotherNote box (one EC2 instance).
#
#   ./deploy/deploy-aws.sh <git-sha>   install that commit's deploy files in /opt/anothernote-admin,
#                                      then run its deploy.sh there. A rollback is the same
#                                      command with an earlier SHA.
#   ./deploy/deploy-aws.sh --status    what runs there now, and the last deploys
#
# Only a commit on origin/main is deployed: one that was reviewed, merged, and built, scanned
# and pushed to ECR by the release workflow. Nothing is built on this machine, and no secret
# passes through it (the box reads its own from SSM).
#
# Settings, the same as playstudy-backend's deploy-aws.sh:
#   PS_DEPLOY_HOST                 ec2-user@<address>; when unset, AWS is asked for it
#   PS_DEPLOY_KEY                  default ~/.ssh/playstudy-turnstile.pem
#   PS_INSTANCE_ID, PS_AWS_REGION  the instance to ask about
# shellcheck disable=SC2029  # the remote commands are put together here, on purpose
set -euo pipefail
INSTANCE_ID=${PS_INSTANCE_ID:-i-02887b9743e873b04}
REGION=${PS_AWS_REGION:-us-east-1}
HOST=${PS_DEPLOY_HOST:-}
KEY=${PS_DEPLOY_KEY:-$HOME/.ssh/playstudy-turnstile.pem}
REMOTE_DIR=/opt/anothernote-admin
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[ $# -eq 1 ] || die "usage: $0 <git-sha> | --status"

if [ "$1" = --status ]; then
  ARG=--status
else
  git -C "$REPO" fetch --quiet origin main
  SHA="$(git -C "$REPO" rev-parse --verify --quiet "$1^{commit}")" || die "$1 is not a commit in this clone"
  git -C "$REPO" merge-base --is-ancestor "$SHA" origin/main ||
    die "$SHA is not on origin/main: only reviewed, merged commits are deployed"
  ARG="$SHA"
fi

if [ -z "$HOST" ]; then
  command -v aws > /dev/null || die "set PS_DEPLOY_HOST, or install the AWS CLI to look the address up"
  IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
  { [ -n "$IP" ] && [ "$IP" != None ]; } || die "instance $INSTANCE_ID has no public address: is it running?"
  HOST="ec2-user@$IP"
fi
[ -f "$KEY" ] || die "SSH key not found: $KEY (set PS_DEPLOY_KEY)"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes -i "$KEY")

if [ "$ARG" != --status ]; then
  echo "==> installing the deploy files of ${SHA:0:12} in $HOST:$REMOTE_DIR"
  LOCAL="$(mktemp -d)"
  trap 'rm -rf "$LOCAL"' EXIT
  for f in docker-compose.yml render-env.sh deploy.sh; do git -C "$REPO" show "$SHA:deploy/$f" > "$LOCAL/$f"; done
  STAGE="$(ssh "${SSH_OPTS[@]}" "$HOST" mktemp -d)"
  scp -q "${SSH_OPTS[@]}" "$LOCAL/docker-compose.yml" "$LOCAL/render-env.sh" "$LOCAL/deploy.sh" "$HOST:$STAGE/"
  ssh "${SSH_OPTS[@]}" "$HOST" "set -e
    sudo install -d -m 0700 -o root -g root $REMOTE_DIR
    sudo install -m 0644 -o root -g root $STAGE/docker-compose.yml $REMOTE_DIR/
    sudo install -m 0755 -o root -g root $STAGE/render-env.sh $STAGE/deploy.sh $REMOTE_DIR/
    rm -rf $STAGE"
fi

echo "==> deploy.sh $ARG on $HOST"
ssh "${SSH_OPTS[@]}" "$HOST" "sudo $REMOTE_DIR/deploy.sh $ARG"
