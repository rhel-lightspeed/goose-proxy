import json
import logging

import httpx

from flask import Flask
from flask import Response


logger = logging.getLogger(__name__)


def _openai_error_response(status_code: int, message: str, error_type: str) -> Response:
    body = json.dumps(
        {
            "error": {
                "message": message,
                "type": error_type,
                "code": status_code,
            }
        }
    )
    return Response(
        response=body,
        status=status_code,
        content_type="application/json",
    )


def _http_status_error_handler(exc: httpx.HTTPStatusError) -> Response:
    status_code = exc.response.status_code
    try:
        body = exc.response.json()
        message = body.get("error", {}).get("message", str(exc))
    except Exception:
        message = exc.response.text or str(exc)

    return _openai_error_response(
        status_code=status_code,
        message=message,
        error_type="api_error",
    )


def _httpx_error_handler(exc: httpx.HTTPError) -> Response:
    return _openai_error_response(
        status_code=502,
        message=str(exc),
        error_type="api_error",
    )


def register_error_handlers(app: Flask) -> None:
    app.register_error_handler(httpx.HTTPStatusError, _http_status_error_handler)
    app.register_error_handler(httpx.HTTPError, _httpx_error_handler)
