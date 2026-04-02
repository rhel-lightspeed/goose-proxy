import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _openai_error_response(
    status_code: int, message: str, error_type: str
) -> JSONResponse:
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


def _http_status_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, httpx.HTTPStatusError)
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


def _httpx_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return _openai_error_response(
        status_code=502,
        message=str(exc),
        error_type="api_error",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with the FastAPI app."""
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(httpx.HTTPStatusError, _http_status_error_handler)
    app.add_exception_handler(httpx.HTTPError, _httpx_error_handler)
