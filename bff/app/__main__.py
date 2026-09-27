"""
`python -m bff.app`: start the BFF with uvicorn, on ADMIN_BIND_HOST:ADMIN_PORT.

This is how the container starts it (0.0.0.0:8080 there). Because this launcher starts
uvicorn itself, the address it binds is exactly what the settings check before allowing
the development identity (which needs 127.0.0.1).
"""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

from . import logs
from .settings import SettingsError, load_settings


def main() -> None:
    host = os.environ.get("ADMIN_BIND_HOST") or "127.0.0.1"
    port = int(os.environ.get("ADMIN_PORT") or "8090")
    os.environ["ADMIN_BIND_HOST"] = host
    # One format for every line, uvicorn's own included (LOG_FORMAT=json in the image).
    logs.configure(os.environ)
    # A configuration mistake is one clear line and exit status 2, not a traceback.
    try:
        load_settings(os.environ, [])
    except SettingsError as e:
        logging.getLogger("bff").critical("cannot start: %s", e)
        sys.exit(2)
    uvicorn.run(
        "bff.app.main:app",
        host=host,
        port=port,
        workers=1,
        # The BFF logs each /bff call itself, without query strings (a search can be an
        # exact email); uvicorn's access log would print them.
        access_log=False,
        server_header=False,
        # Nothing here needs the visitor's address, so no forwarded header is believed.
        proxy_headers=False,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        log_config=None,
    )


if __name__ == "__main__":
    main()
