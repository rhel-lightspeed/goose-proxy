"""CLI entrypoint for running goose-proxy with uvicorn."""

import uvicorn

from goose_proxy.config import get_settings


def serve():
    """Entry point for running the application with uvicorn."""
    settings = get_settings()

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
