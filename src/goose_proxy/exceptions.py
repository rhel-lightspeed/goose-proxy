import json
import logging
import urllib.error

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse


logger = logging.getLogger("uvicorn.error")


def _openai_error_response(status_code: int, message: str, error_type: str) -> JSONResponse:
    """Build an OpenAI-compatible error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "code": status_code,
            }
        },
    )


def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)

    return _openai_error_response(
        status_code=exc.status_code,
        message=str(exc.detail),
        error_type="invalid_request_error" if exc.status_code < 500 else "server_error",
    )


def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, urllib.error.HTTPError)
    body = exc.read().decode()

    logger.debug(
        "Backend HTTP error\n\tURL: %s\n\tResponse status: %s %s\n\tResponse headers: %s\n\tResponse body: %s",
        exc.url,
        exc.code,
        exc.reason,
        dict(exc.headers) if exc.headers else {},
        body,
    )

    try:
        data = json.loads(body)
        message = data.get("error", {}).get("message", str(exc))
    except (json.JSONDecodeError, ValueError):
        message = body or str(exc)

    return _openai_error_response(
        status_code=exc.code,
        message=message,
        error_type="api_error",
    )


def _url_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, urllib.error.URLError)

    logger.debug("Backend connection error: %s", exc.reason)

    return _openai_error_response(
        status_code=502,
        message=str(exc.reason),
        error_type="api_error",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(urllib.error.HTTPError, _http_error_handler)
    app.add_exception_handler(urllib.error.URLError, _url_error_handler)
