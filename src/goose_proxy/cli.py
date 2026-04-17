"""CLI entrypoint for running goose-proxy with uvicorn."""

import sys

import uvicorn

from goose_proxy.config import get_settings
from goose_proxy.config import tomllib


def serve():
    """Entry point for running the application with uvicorn."""
    try:
        settings = get_settings()
    except tomllib.TOMLDecodeError as err:
        sys.exit(f"Problem reading config file: {err}")

    # Use import string for reload mode so uvicorn can re-import the app.
    from goose_proxy.app import app

    uvicorn.run(
        "goose_proxy.app:app" if settings.server.reload else app,
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        workers=settings.server.workers,
        log_level=settings.logging.level.lower(),
    )
