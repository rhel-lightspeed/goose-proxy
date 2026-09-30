"""Tests for exception handlers — all errors must return OpenAI-compatible JSON."""

import json

from unittest.mock import MagicMock

import httpx

from fastapi import HTTPException

from goose_proxy.exceptions import _cert_error_handler
from goose_proxy.exceptions import _http_exception_handler
from goose_proxy.exceptions import _http_status_error_handler
from goose_proxy.exceptions import _request_error_handler
from goose_proxy.exceptions import CertificateInitializationError


def _dummy_request():
    return MagicMock()


def _make_http_status_error(status_code: int, body: dict) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError matching what httpx raises for backend errors."""
    request = httpx.Request("POST", "https://backend/v1/responses")
    response = httpx.Response(status_code, json=body, request=request)
    return httpx.HTTPStatusError(str(status_code), request=request, response=response)


class TestHttpExceptionHandler:
    def test_4xx_returns_invalid_request_error(self):
        exc = HTTPException(status_code=400, detail="Bad request body")

        resp = _http_exception_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 400
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["message"] == "Bad request body"
        assert body["error"]["code"] == 400

    def test_404_returns_invalid_request_error(self):
        exc = HTTPException(status_code=404, detail="Not found")

        resp = _http_exception_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert body["error"]["type"] == "invalid_request_error"

    def test_499_returns_invalid_request_error(self):
        exc = HTTPException(status_code=499, detail="Client closed")

        resp = _http_exception_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert body["error"]["type"] == "invalid_request_error"

    def test_500_returns_server_error(self):
        exc = HTTPException(status_code=500, detail="Internal error")

        resp = _http_exception_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 500
        assert body["error"]["type"] == "server_error"
        assert body["error"]["message"] == "Internal error"

    def test_502_returns_server_error(self):
        exc = HTTPException(status_code=502, detail="Bad gateway")

        resp = _http_exception_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert body["error"]["type"] == "server_error"


class TestHttpStatusErrorHandler:
    def test_extracts_message_from_json_error(self):
        """Error message is extracted from the backend's OpenAI-format error body."""
        exc = _make_http_status_error(422, {"error": {"message": "Invalid parameters"}})

        resp = _http_status_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 422
        assert body["error"]["message"] == "Invalid parameters"
        assert body["error"]["type"] == "api_error"

    def test_falls_back_to_exc_str_when_no_error_key(self):
        """Falls back to the exception string when the body has no 'error' key."""
        exc = _make_http_status_error(503, {"detail": "Service unavailable"})

        resp = _http_status_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 503
        assert body["error"]["message"]

    def test_preserves_status_code(self):
        """Backend status code is forwarded to the client."""
        exc = _make_http_status_error(429, {"error": {"message": "Rate limited"}})

        resp = _http_status_error_handler(_dummy_request(), exc)

        assert resp.status_code == 429

    def test_404_propagates(self):
        """Backend 404 is forwarded with the original error message."""
        exc = _make_http_status_error(404, {"error": {"message": "Model not found"}})

        resp = _http_status_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 404
        assert body["error"]["message"] == "Model not found"


class TestRequestErrorHandler:
    def test_connection_error_returns_502(self):
        """Backend connection failures return a 502 error."""
        exc = httpx.ConnectError("All connection attempts failed")

        resp = _request_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 502
        assert body["error"]["type"] == "api_error"

    def test_timeout_error_returns_502(self):
        """Backend timeouts return a 502 error."""
        exc = httpx.ReadTimeout("Timed out")

        resp = _request_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 502
        assert body["error"]["type"] == "api_error"


class TestCertErrorHandler:
    def test_cert_init_error_returns_502(self):
        cause = FileNotFoundError("[Errno 2] No such file or directory: '/etc/pki/consumer/cert.pem'")
        exc = CertificateInitializationError()
        exc.__cause__ = cause

        resp = _cert_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 502
        assert body["error"]["type"] == "server_error"
        assert "System is not registered" in body["error"]["message"]
        assert "subscription-manager register" in body["error"]["message"]
        # Raw exception details must not leak to the client
        assert "/etc/pki" not in body["error"]["message"]
