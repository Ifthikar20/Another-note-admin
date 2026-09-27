"""
Signing each call to the admin API (build specification 5.8.2).

Every call carries the service token, who is asking (actor and role), a fresh request id
and the time, and an HMAC over all of that plus the method, the exact path and query, and
a digest of the body:

    X-Admin-Signature = base64url(HMAC-SHA256(ADMIN_SIGNING_KEY,
        METHOD \\n PATH_WITH_QUERY \\n TIMESTAMP \\n ACTOR \\n ROLE \\n REQUEST_ID \\n SHA256_HEX(BODY)))

Exact form, so the admin API can check it byte for byte:
  - the key is ADMIN_SIGNING_KEY's text as UTF-8 bytes (not hex-decoded);
  - METHOD is upper case; PATH_WITH_QUERY is the request target as sent on the wire
    (`/admin/v1/users?kind=standard&limit=50`, percent-encoded, no host);
  - TIMESTAMP is whole unix seconds in decimal; SHA256_HEX is lower-case hex, and the
    digest of an empty body is that of the empty string;
  - the seven lines are joined with a single "\\n", with no trailing newline;
  - base64url is RFC 4648 section 5 without "=" padding.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from typing import Optional

HEADER_ACTOR = "X-Admin-Actor"
HEADER_ROLE = "X-Admin-Role"
HEADER_REQUEST_ID = "X-Admin-Request-Id"
HEADER_TIMESTAMP = "X-Admin-Timestamp"
HEADER_SIGNATURE = "X-Admin-Signature"


def body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def canonical_message(
    method: str, path_with_query: str, timestamp: int, actor: str, role: str, request_id: str, body: bytes
) -> bytes:
    return "\n".join(
        [method.upper(), path_with_query, str(int(timestamp)), actor, role, request_id, body_digest(body)]
    ).encode("utf-8")


def signature(key: str, message: bytes) -> str:
    mac = hmac.new(key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def signed_headers(
    *,
    service_token: str,
    signing_key: str,
    method: str,
    path_with_query: str,
    actor: str,
    role: str,
    body: bytes = b"",
    timestamp: Optional[int] = None,
    request_id: Optional[str] = None,
) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else int(timestamp)
    rid = request_id or str(uuid.uuid4())
    message = canonical_message(method, path_with_query, ts, actor, role, rid, body)
    return {
        "Authorization": f"Bearer {service_token}",
        HEADER_ACTOR: actor,
        HEADER_ROLE: role,
        HEADER_REQUEST_ID: rid,
        HEADER_TIMESTAMP: str(ts),
        HEADER_SIGNATURE: signature(signing_key, message),
    }
