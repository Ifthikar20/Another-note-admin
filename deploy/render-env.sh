#!/usr/bin/env bash
# Write .env for the admin compose project from SSM Parameter Store: every parameter under
# /anothernote/prod/admin/ (SecureString for secrets, String for settings), read with the
# instance's IAM role. No secret is typed into a shell, kept in git, or copied between
# machines, and the file is root's alone (0600).
#
#   sudo ./render-env.sh          (deploy.sh runs it, with ADMIN_WEB_VERSION set)
#
# Environment: SSM_PREFIX (default /anothernote/prod/admin/), ENV_FILE (default .env beside
# this script), AWS_REGION (default: this instance's region), ADMIN_WEB_VERSION (the image
# tag to run; written into the file when set). Prints names, never values.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PREFIX="${SSM_PREFIX:-/anothernote/prod/admin/}"
OUT="${ENV_FILE:-.env}"
REQUIRED=(ADMIN_DATABASE_URL ADMIN_SERVICE_TOKEN ADMIN_SIGNING_KEY ADMIN_LOOKUP_PEPPER
  CF_ACCESS_TEAM_DOMAIN CF_ACCESS_AUD ADMIN_MEMBERS CLOUDFLARE_TUNNEL_TOKEN ADMIN_WEB_IMAGE)

region() {
  if [ -n "${AWS_REGION:-}" ]; then echo "$AWS_REGION"; return; fi
  local token  # IMDSv2: the instance may (and should) refuse version 1
  token=$(curl -sf -m 2 -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' http://169.254.169.254/latest/api/token) || return 1
  curl -sf -m 2 -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/placement/region
}
REGION=$(region) || { echo "set AWS_REGION: this is not an EC2 instance, or its metadata service is off" >&2; exit 1; }

umask 077
RAW=$(mktemp "${OUT}.raw.XXXXXX")
TMP=$(mktemp "${OUT}.new.XXXXXX")
trap 'rm -f "$RAW" "$TMP"' EXIT

aws ssm get-parameters-by-path --region "$REGION" --path "$PREFIX" --recursive --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text > "$RAW"

# KEY 'VALUE': compose reads a single-quoted value literally (no ${...} expansion). Values
# that could not survive that are refused rather than mangled.
write() {
  case "$2" in
    *"'"* | *\\* | *$'\r'*)
      echo "$3 holds a quote or a backslash: make it again from letters, digits, - and _ (openssl rand -hex 32)" >&2
      exit 1
      ;;
  esac
  printf "%s='%s'\n" "$1" "$2" >> "$TMP"
}

names=()
while IFS=$'\t' read -r name value; do
  [ -n "$name" ] || continue
  key="${name##*/}"
  case "$key" in
    '' | [0-9]* | *[!A-Z0-9_]*) echo "skipping $name: not an environment variable name" >&2; continue ;;
  esac
  write "$key" "$value" "$name"
  names+=("$key")
done < "$RAW"

has() { grep -q "^$1=" "$TMP"; }
has AWS_REGION || write AWS_REGION "$REGION" AWS_REGION
if [ -n "${ADMIN_WEB_VERSION:-}" ]; then
  [[ "$ADMIN_WEB_VERSION" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || { echo "ADMIN_WEB_VERSION is not an image tag" >&2; exit 1; }
  ! has ADMIN_WEB_VERSION || { echo "ADMIN_WEB_VERSION is chosen at deploy time: delete ${PREFIX}ADMIN_WEB_VERSION from SSM" >&2; exit 1; }
  write ADMIN_WEB_VERSION "$ADMIN_WEB_VERSION" ADMIN_WEB_VERSION
fi

missing=()
for required in "${REQUIRED[@]}"; do has "$required" || missing+=("${PREFIX}${required}"); done
[ ${#missing[@]} -eq 0 ] || { echo "missing in SSM: ${missing[*]}" >&2; exit 1; }

chmod 600 "$TMP"
mv -f "$TMP" "$OUT"
echo "wrote $OUT: ${names[*]}"
