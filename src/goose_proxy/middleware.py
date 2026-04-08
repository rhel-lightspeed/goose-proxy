from __future__ import annotations

import json

from typing import Any
from typing import Iterable


class TimeoutMiddleware:
    """WSGI middleware that enforces a timeout on the backend's initial response.

    In the WSGI (synchronous) world, the httpx.Client timeout handles the
    actual network-level deadline. This middleware provides an additional
    safety net by catching any TimeoutError that propagates up and returning
    a standardised 504 response in OpenAI-compatible format.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        try:
            return self.app(environ, start_response)
        except TimeoutError:
            body = json.dumps(
                {
                    "error": {
                        "message": "Request timed out while waiting for the backend.",
                        "type": "server_error",
                        "code": 504,
                    }
                }
            ).encode("utf-8")
            start_response(
                "504 Gateway Timeout",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]
