"""ADMIN_MEMBERS and the role table (5.8.3); the start-up rules of the settings (6.3.6)."""

from __future__ import annotations

import pytest

from bff.app.members import CAPABILITIES, Member, MembersError, parse_members
from bff.app.settings import SettingsError, detect_bind_host, load_settings

SECRET_A = "a" * 64
SECRET_B = "b" * 64


def test_members_parse_email_role_pairs():
    assert parse_members(" Jane@AnotherNote.app:Support ,sam@anothernote.app:owner,, ") == {
        "jane@anothernote.app": "support",
        "sam@anothernote.app": "owner",
    }
    assert parse_members("") == {}


@pytest.mark.parametrize(
    "raw",
    [
        "jane@anothernote.app",
        "jane@anothernote.app:admin",
        "not-an-email:owner",
        "a@b.c:owner,a@b.c:viewer",
        "ja ne@x.y:owner",
        "jané@x.y:owner",
    ],
)
def test_bad_member_lists_are_refused(raw):
    with pytest.raises(MembersError):
        parse_members(raw)


# 5.8.3, row by row: (capability, owner, support, analyst, viewer)
TABLE = [
    ("metrics.read", 1, 1, 1, 1),
    ("users.read", 1, 1, 1, 1),
    ("users.reveal_email", 1, 1, 0, 0),
    ("tickets.read", 1, 1, 0, 1),
    ("tickets.write", 1, 1, 0, 0),
    ("users.sign_out", 1, 1, 0, 0),
    ("users.set_active", 1, 0, 0, 0),
    ("plans.write", 1, 0, 0, 0),
    ("security.read", 1, 1, 0, 0),
    # the event-by-event activity log (who did what in the app): support+
    ("activity.read", 1, 1, 0, 0),
    ("audit.read", 1, 0, 0, 0),
    ("settings.read", 1, 0, 0, 0),
    # 5.8.4 is stricter than 5.8.3 for these two
    ("users.tickets", 1, 1, 0, 0),
    ("tickets.events", 1, 1, 0, 0),
]


@pytest.mark.parametrize("capability,owner,support,analyst,viewer", TABLE)
def test_the_role_table(capability, owner, support, analyst, viewer):
    for role, allowed in (("owner", owner), ("support", support), ("analyst", analyst), ("viewer", viewer)):
        assert Member("x@y.z", role).can(capability) is bool(allowed), (capability, role)


def test_every_capability_is_in_the_table():
    assert {row[0] for row in TABLE} | {"plans.read", "orgs.read", "users.auth_events"} == set(CAPABILITIES)


# --- settings -----------------------------------------------------------------------------
def env(**overrides: str) -> dict[str, str]:
    base = {
        "ENVIRONMENT": "production",
        "ADMIN_API_URL": "http://admin-api:8001",
        "ADMIN_SERVICE_TOKEN": SECRET_A,
        "ADMIN_SIGNING_KEY": SECRET_B,
        "CF_ACCESS_TEAM_DOMAIN": "anothernote.cloudflareaccess.com",
        "CF_ACCESS_AUD": "aud",
        "ADMIN_MEMBERS": "sam@anothernote.app:owner",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def dev_env(**overrides: str) -> dict[str, str]:
    base = {
        "ENVIRONMENT": "development",
        "CF_ACCESS_TEAM_DOMAIN": "",
        "CF_ACCESS_AUD": "",
        "ADMIN_MEMBERS": "",
        "ADMIN_DEV_IDENTITY": "dev@localhost:owner",
    }
    return env(**{**base, **overrides})


def test_a_complete_production_environment_loads():
    s = load_settings(env(CF_ACCESS_TEAM_DOMAIN="https://AnotherNote.cloudflareaccess.com/"), ["x"])
    assert s.is_production and s.access_enabled and s.dev_identity is None
    assert s.cf_team_domain == "anothernote.cloudflareaccess.com"
    assert s.members == {"sam@anothernote.app": "owner"}


def test_environment_defaults_to_production():
    s = load_settings({k: v for k, v in env().items() if k != "ENVIRONMENT"}, ["x"])
    assert s.is_production


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"ADMIN_SERVICE_TOKEN": None}, "missing ADMIN_SERVICE_TOKEN"),
        ({"ADMIN_SIGNING_KEY": "short"}, "too short"),
        ({"ADMIN_SIGNING_KEY": SECRET_A}, "must be different"),
        ({"CF_ACCESS_AUD": None}, "both"),
        ({"CF_ACCESS_TEAM_DOMAIN": None, "CF_ACCESS_AUD": None}, "production needs CF_ACCESS"),
        ({"ADMIN_MEMBERS": ""}, "production needs ADMIN_MEMBERS"),
        ({"ADMIN_MEMBERS": "sam@anothernote.app:root"}, "ADMIN_MEMBERS"),
        ({"ADMIN_API_URL": "http://admin-api:8001/v1"}, "origin only"),
        ({"ADMIN_API_URL": "admin-api:8001"}, "must be a URL"),
        ({"ENVIRONMENT": "staging"}, "ENVIRONMENT"),
        ({"ADMIN_DEV_IDENTITY": "dev@localhost:owner", "ADMIN_BIND_HOST": "127.0.0.1"}, "development only"),
    ],
)
def test_production_refuses_to_start_misconfigured(overrides, message):
    with pytest.raises(SettingsError, match=message):
        load_settings(env(**overrides), ["x"])


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]", "127.0.0.2"])
def test_dev_identity_works_on_loopback(host):
    s = load_settings(dev_env(ADMIN_BIND_HOST=host), ["x"])
    assert s.dev_identity == Member("dev@localhost", "owner")
    assert not s.access_enabled


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "admin-web", ""])
def test_dev_identity_refused_unless_loopback(host):
    with pytest.raises(SettingsError, match="bound to 127.0.0.1"):
        load_settings(dev_env(ADMIN_BIND_HOST=host), ["x"])


def test_dev_identity_needs_a_valid_pair():
    with pytest.raises(SettingsError, match="ADMIN_DEV_IDENTITY"):
        load_settings(dev_env(ADMIN_BIND_HOST="127.0.0.1", ADMIN_DEV_IDENTITY="dev@localhost:god"), ["x"])


def test_development_without_any_identity_refuses_to_start():
    with pytest.raises(SettingsError, match="ADMIN_DEV_IDENTITY"):
        load_settings(dev_env(ADMIN_DEV_IDENTITY=""), ["x"])


@pytest.mark.parametrize(
    "argv,environ,expected",
    [
        (["/v/bin/uvicorn", "bff.app.main:app", "--port", "8090"], {}, "127.0.0.1"),
        (["/v/bin/uvicorn", "bff.app.main:app", "--host", "0.0.0.0"], {}, "0.0.0.0"),
        (["/v/bin/uvicorn", "bff.app.main:app", "--host=::"], {}, "::"),
        (["/v/bin/uvicorn", "bff.app.main:app"], {"UVICORN_HOST": "0.0.0.0"}, "0.0.0.0"),
        (
            ["/v/lib/python3.11/site-packages/uvicorn/__main__.py", "bff.app.main:app", "--host", "10.0.0.5"],
            {},
            "10.0.0.5",
        ),
        (["C:\\v\\Scripts\\uvicorn.exe", "bff.app.main:app"], {}, "127.0.0.1"),
        (["/v/bin/uvicorn", "bff.app.main:app", "--uds", "/tmp/s"], {}, None),
        (["/v/bin/uvicorn", "bff.app.main:app", "--fd", "3"], {}, None),
        (["/v/bin/gunicorn", "-b", "0.0.0.0:8090", "bff.app.main:app"], {}, "0.0.0.0"),
        (["/v/bin/gunicorn", "--bind=127.0.0.1:8090", "bff.app.main:app"], {}, "127.0.0.1"),
        (["/v/bin/gunicorn", "--bind", "unix:/tmp/s"], {}, None),
        (["/app/bff/app/__main__.py"], {"ADMIN_BIND_HOST": "0.0.0.0"}, "0.0.0.0"),
        (["/some/other/server"], {}, None),
    ],
)
def test_bind_host_detection(argv, environ, expected):
    assert detect_bind_host(environ, argv) == expected


def test_the_uvicorn_command_line_beats_a_stale_bind_host_variable():
    # Someone exported ADMIN_BIND_HOST=127.0.0.1 but started uvicorn on all interfaces.
    with pytest.raises(SettingsError, match="bound to 127.0.0.1"):
        load_settings(dev_env(ADMIN_BIND_HOST="127.0.0.1"), ["/v/bin/uvicorn", "bff.app.main:app", "--host", "0.0.0.0"])


def test_public_origin_must_be_an_origin():
    assert (
        load_settings(env(ADMIN_PUBLIC_ORIGIN="https://admin.anothernote.app"), ["x"]).public_origin
        == "https://admin.anothernote.app"
    )
    with pytest.raises(SettingsError):
        load_settings(env(ADMIN_PUBLIC_ORIGIN="https://admin.anothernote.app/x"), ["x"])
