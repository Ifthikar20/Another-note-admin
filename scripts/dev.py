"""
Run the admin app on this machine, in one command (Windows, macOS, Linux):

    python scripts/dev.py            the stand-in admin API (:8001) and the BFF (:8090)
    python scripts/dev.py --web      ... and the Vite dev server (:8080): open http://127.0.0.1:8080
    python scripts/dev.py --role support
                                     sign in as a different role (owner, support, analyst, viewer)
    python scripts/dev.py --admin-api http://127.0.0.1:8001 --no-stub
                                     use the real admin API from playstudy-backend instead

Everything binds 127.0.0.1 only, and uses the development settings in dev.env. Ctrl+C
stops it all.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--web", action="store_true", help="also run the Vite dev server on :8080")
    parser.add_argument("--role", choices=["owner", "support", "analyst", "viewer"], default="owner")
    parser.add_argument("--no-stub", action="store_true", help="don't start the stand-in admin API")
    parser.add_argument("--admin-api", default=None, help="the admin API's URL (default: the stand-in on :8001)")
    args = parser.parse_args()

    env = {**os.environ, **load_env(ROOT / "dev.env")}
    env["ADMIN_DEV_IDENTITY"] = f"dev@localhost:{args.role}"
    if args.admin_api:
        env["ADMIN_API_URL"] = args.admin_api
    env.setdefault("STUB_LIVE_EVENTS", "1")
    python = sys.executable
    procs: list[subprocess.Popen[bytes]] = []

    def start(name: str, cmd: list[str], cwd: Path = ROOT) -> None:
        print(f"[dev] {name}: {' '.join(cmd)}", flush=True)
        procs.append(subprocess.Popen(cmd, cwd=cwd, env=env))  # noqa: S603 (fixed commands, not input)

    if not args.no_stub:
        start(
            "stand-in admin API",
            [python, "-m", "uvicorn", "devstub.app:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"],
        )
        time.sleep(1.5)
    start(
        "BFF",
        [
            python,
            "-m",
            "uvicorn",
            "bff.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8090",
            "--no-access-log",
            "--no-server-header",
        ],
    )
    if args.web:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            print("[dev] npm not found: install Node.js 22, or run the SPA yourself", flush=True)
        else:
            start("web", [npm, "run", "dev"], cwd=ROOT / "web")
    print(
        "[dev] open http://127.0.0.1:8080 (with --web) or http://127.0.0.1:8090 (after `npm run build` in web/)",
        flush=True,
    )
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
