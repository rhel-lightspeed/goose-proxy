"""Exception hierarchy and OpenAI-compatible error response builders."""

import logging

import openai

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class GooseProxyError(Exception):
    """Base exception for all goose-proxy errors."""


class CertificateInitializationError(GooseProxyError):
    """Raised when backend certificate initialization fails."""


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
    """Handle HTTP error responses from the backend (4xx/5xx)."""
    assert isinstance(exc, openai.APIStatusError)

    status_code = exc.status_code
    logger.warning(
        "Backend HTTP error\n\tURL: %s\n\tStatus: %s\n\tBody: %s",
        exc.request.url,
        status_code,
        exc.response.text,
    )

    try:
        data = exc.response.json()
        message = data.get("error", {}).get("message", str(exc))
    except Exception:
        message = exc.response.text or str(exc)

    return _openai_error_response(
        status_code=status_code,
        message=message,
        error_type="api_error",
    )


def _api_connection_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Handle connection and timeout failures (backend unreachable)."""
    assert isinstance(exc, openai.APIConnectionError)

    logger.warning("Backend connection error: %s", exc)

    return _openai_error_response(
        status_code=502,
        message=str(exc),
        error_type="api_error",
    )


def _cert_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, CertificateInitializationError)

    logger.warning("Certificate error: %s", exc.__cause__)

    return _openai_error_response(
        status_code=502,
        message=(
            "System is not registered. Failed to initialize certificate authentication. "
            "Register this system with 'subscription-manager register' and try again."
        ),
        error_type="server_error",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application."""
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(openai.APIStatusError, _api_status_error_handler)
    app.add_exception_handler(openai.APIConnectionError, _api_connection_error_handler)
    app.add_exception_handler(CertificateInitializationError, _cert_error_handler)
