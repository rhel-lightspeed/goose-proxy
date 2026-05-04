"""CLI entrypoint for running goose-proxy with uvicorn."""

import logging
import os
import sys

import uvicorn

from pydantic import ValidationError

from goose_proxy.config import get_settings
from goose_proxy.config import tomllib


#: The first file descriptor passed by systemd socket activation.
SD_LISTEN_FDS_START = 3

logger = logging.getLogger(__name__)


def _is_socket_activated() -> bool:
    """Check whether the process was started via systemd socket activation.

    The sd_listen_fds protocol sets LISTEN_FDS to the number of file
    descriptors passed and LISTEN_PID to the PID of the target process.
    """
    listen_fds = os.environ.get("LISTEN_FDS")
    listen_pid = os.environ.get("LISTEN_PID")

    if listen_fds is None or listen_pid is None:
        return False

    # LISTEN_PID must match our PID (guards against inherited env vars).
    if int(listen_pid) != os.getpid():
        return False

    return int(listen_fds) >= 1


def serve():
    """Entry point for running the application with uvicorn."""
    try:
        settings = get_settings()
    except (tomllib.TOMLDecodeError, ValidationError) as err:
        sys.exit(f"Problem reading config file: {err}")

    if _is_socket_activated():
        if settings.server.reload:
            logger.warning("The 'reload' setting is ignored under systemd socket activation.")

        uvicorn.run(
            "goose_proxy.app:app",
            fd=SD_LISTEN_FDS_START,
            workers=settings.server.workers,
            log_level=settings.logging.level.lower(),
        )
    else:
        uvicorn.run(
            "goose_proxy.app:app",
            host=settings.server.host,
            port=settings.server.port,
            reload=settings.server.reload,
            workers=settings.server.workers,
            log_level=settings.logging.level.lower(),
        )
