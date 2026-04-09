import logging
import typing as t

import openai

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


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


def _api_status_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, openai.APIStatusError)
    message = str(exc)
    body = t.cast(dict[str, t.Any], exc.body) if isinstance(exc.body, dict) else None
    if body:
        error_info = body.get("error")
        if isinstance(error_info, dict) and "message" in error_info:
            message = error_info["message"]

    return _openai_error_response(
        status_code=exc.status_code,
        message=message,
        error_type="api_error",
    )


def _api_connection_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return _openai_error_response(
        status_code=502,
        message=str(exc),
        error_type="api_error",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with the FastAPI app."""
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(openai.APIStatusError, _api_status_error_handler)
    app.add_exception_handler(openai.APIConnectionError, _api_connection_error_handler)
