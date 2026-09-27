"""
The BFF's configuration, read once from the environment at start-up.

Production is the default: a missing ENVIRONMENT never turns the development identity on.
Anything misconfigured raises SettingsError while the app is being imported, so a
half-configured BFF never serves a request.

Development identity (ADMIN_DEV_IDENTITY=dev@localhost:owner) stands in for Cloudflare
Access on a developer's machine. It is refused unless ENVIRONMENT=development AND the
server is bound to a loopback address; at request time it is also applied only to
connections that come from the machine itself.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlsplit

from .members import Member, MembersError, parse_members, parse_pair

VERSION = "0.1.0"

ENVIRONMENTS = ("production", "development")
MIN_SECRET_LENGTH = 32  # `openssl rand -hex 32` gives 64


class SettingsError(RuntimeError):
    """The environment does not describe a BFF that is safe to start."""


@dataclass(frozen=True)
class Settings:
    environment: str
    admin_api_url: str
    service_token: str
    signing_key: str
    cf_team_domain: Optional[str] = None
    cf_aud: Optional[str] = None
    members: Mapping[str, str] = field(default_factory=dict)
    dev_identity: Optional[Member] = None
    # The site's own origin (https://admin.anothernote.app), for the same-origin check on
    # changes. Unset, the Origin header is compared with the Host header instead.
    public_origin: Optional[str] = None
    static_dir: Optional[str] = None
    version: str = VERSION

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def access_enabled(self) -> bool:
        return bool(self.cf_team_domain and self.cf_aud)


def is_loopback(host: Optional[str]) -> bool:
    if not host:
        return False
    host = host.strip().strip("[]")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _flag(args: Sequence[str], *names: str) -> Optional[str]:
    """The value of `--name value` or `--name=value` in a command line, last one winning."""
    value = None
    for i, arg in enumerate(args):
        for name in names:
            if arg == name and i + 1 < len(args):
                value = args[i + 1]
            elif arg.startswith(name + "="):
                value = arg[len(name) + 1 :]
    return value


def detect_bind_host(env: Mapping[str, str], argv: Sequence[str]) -> Optional[str]:
    """The address this process serves on, as far as it can be known before it binds.

    Under the uvicorn command line: its --host (or UVICORN_HOST), else uvicorn's default,
    127.0.0.1. Under gunicorn: the host of --bind. Under our own launcher
    (`python -m bff.app`), which starts uvicorn itself: ADMIN_BIND_HOST, which it sets to
    exactly what it binds. None when it cannot be told (a socket handed over with --fd or
    --uds, or an unknown server), which the development identity treats as "not loopback".
    """
    prog = argv[0] if argv else ""
    args = list(argv[1:])
    if "uvicorn" in os.path.basename(prog) or "uvicorn" in prog.replace("\\", "/").split("/")[-2:-1]:
        if _flag(args, "--fd") or _flag(args, "--uds"):
            return None
        return _flag(args, "--host") or env.get("UVICORN_HOST") or "127.0.0.1"
    if "gunicorn" in os.path.basename(prog):
        bind = _flag(args, "--bind", "-b")
        if not bind:
            return "127.0.0.1"
        if bind.startswith(("unix:", "fd://")):
            return None
        host = bind.rsplit(":", 1)[0] if ":" in bind else bind
        return host.strip("[]")
    return env.get("ADMIN_BIND_HOST")


def _origin_only(url: str, name: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise SettingsError(f"{name} must be a URL such as http://admin-api:8001 or https://admin.anothernote.app")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        # The request path is part of what is signed: a prefix here would sign one path
        # and send another.
        raise SettingsError(f"{name} must be an origin only (scheme, host and port), not {url!r}")
    return f"{parts.scheme}://{parts.netloc}"


def _team_domain(raw: str) -> str:
    domain = raw.strip().lower()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix) :]
    domain = domain.rstrip("/")
    if not domain or "/" in domain or ":" in domain or "." not in domain:
        raise SettingsError("CF_ACCESS_TEAM_DOMAIN must be a host name such as anothernote.cloudflareaccess.com")
    return domain


def load_settings(env: Optional[Mapping[str, str]] = None, argv: Optional[Sequence[str]] = None) -> Settings:
    env = os.environ if env is None else env
    argv = sys.argv if argv is None else argv

    environment = (env.get("ENVIRONMENT") or "production").strip().lower()
    if environment not in ENVIRONMENTS:
        raise SettingsError(f"ENVIRONMENT must be one of {', '.join(ENVIRONMENTS)}, not {environment!r}")
    production = environment == "production"

    missing = [name for name in ("ADMIN_API_URL", "ADMIN_SERVICE_TOKEN", "ADMIN_SIGNING_KEY") if not env.get(name)]
    if missing:
        raise SettingsError(f"missing {', '.join(missing)}")
    admin_api_url = _origin_only(env["ADMIN_API_URL"].strip(), "ADMIN_API_URL")
    service_token = env["ADMIN_SERVICE_TOKEN"].strip()
    signing_key = env["ADMIN_SIGNING_KEY"].strip()
    if service_token == signing_key:
        raise SettingsError("ADMIN_SERVICE_TOKEN and ADMIN_SIGNING_KEY must be different secrets")
    if production:
        for name, value in (("ADMIN_SERVICE_TOKEN", service_token), ("ADMIN_SIGNING_KEY", signing_key)):
            if len(value) < MIN_SECRET_LENGTH:
                raise SettingsError(f"{name} is too short: make it with `openssl rand -hex 32`")

    try:
        members = parse_members(env.get("ADMIN_MEMBERS", ""))
    except MembersError as e:
        raise SettingsError(f"ADMIN_MEMBERS: {e}") from None

    team = env.get("CF_ACCESS_TEAM_DOMAIN", "").strip()
    aud = env.get("CF_ACCESS_AUD", "").strip()
    if bool(team) != bool(aud):
        raise SettingsError("set both CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD, or neither")
    team_domain = _team_domain(team) if team else None

    dev_identity = None
    raw_dev = env.get("ADMIN_DEV_IDENTITY", "").strip()
    if raw_dev:
        if production:
            raise SettingsError("ADMIN_DEV_IDENTITY is for development only: remove it (ENVIRONMENT is production)")
        bind_host = detect_bind_host(env, argv)
        if not is_loopback(bind_host):
            raise SettingsError(
                "ADMIN_DEV_IDENTITY works only on a server bound to 127.0.0.1 "
                f"(this one is bound to {bind_host or 'an address that cannot be determined'})"
            )
        try:
            dev_identity = parse_pair(raw_dev)
        except MembersError as e:
            raise SettingsError(f"ADMIN_DEV_IDENTITY: {e}") from None

    if production and not (team_domain and aud):
        raise SettingsError("production needs CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD")
    if production and not members:
        raise SettingsError("production needs ADMIN_MEMBERS (email:role pairs)")
    if not dev_identity and not team_domain:
        raise SettingsError("set ADMIN_DEV_IDENTITY (development) or CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD")

    public_origin = None
    if env.get("ADMIN_PUBLIC_ORIGIN", "").strip():
        public_origin = _origin_only(env["ADMIN_PUBLIC_ORIGIN"].strip(), "ADMIN_PUBLIC_ORIGIN")

    static_dir = env.get("ADMIN_STATIC_DIR") or _default_static_dir()
    return Settings(
        environment=environment,
        admin_api_url=admin_api_url,
        service_token=service_token,
        signing_key=signing_key,
        cf_team_domain=team_domain,
        cf_aud=aud or None,
        members=members,
        dev_identity=dev_identity,
        public_origin=public_origin,
        static_dir=static_dir if static_dir and os.path.isdir(static_dir) else None,
    )


def _default_static_dir() -> str:
    """web/dist next to bff/ in a checkout; the Dockerfile sets ADMIN_STATIC_DIR instead."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "web", "dist"))
