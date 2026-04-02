"""Tests for exception handlers."""

from unittest.mock import MagicMock

import httpx
from fastapi import HTTPException

from goose_proxy.exceptions import (
    _http_exception_handler,
    _http_status_error_handler,
    _httpx_error_handler,
)


def _dummy_request():
    return MagicMock()


class TestHttpExceptionHandler:
    def test_4xx_returns_invalid_request_error(self):
        exc = HTTPException(status_code=400, detail="Bad request body")
        resp = _http_exception_handler(_dummy_request(), exc)
        assert resp.status_code == 400
        assert resp.body is not None
        body = _parse(resp)
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["message"] == "Bad request body"
        assert body["error"]["code"] == 400

    def test_404_returns_invalid_request_error(self):
        exc = HTTPException(status_code=404, detail="Not found")
        resp = _http_exception_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert body["error"]["type"] == "invalid_request_error"

    def test_499_returns_invalid_request_error(self):
        exc = HTTPException(status_code=499, detail="Client closed")
        resp = _http_exception_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert body["error"]["type"] == "invalid_request_error"

    def test_500_returns_server_error(self):
        exc = HTTPException(status_code=500, detail="Internal error")
        resp = _http_exception_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 500
        assert body["error"]["type"] == "server_error"
        assert body["error"]["message"] == "Internal error"

    def test_502_returns_server_error(self):
        exc = HTTPException(status_code=502, detail="Bad gateway")
        resp = _http_exception_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert body["error"]["type"] == "server_error"


class TestHttpStatusErrorHandler:
    def test_extracts_message_from_json_error(self):
        response = httpx.Response(
            status_code=422,
            json={"error": {"message": "Invalid parameters"}},
        )
        response._request = httpx.Request("POST", "http://test")
        exc = httpx.HTTPStatusError(
            message="Unprocessable",
            request=response._request,
            response=response,
        )
        resp = _http_status_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 422
        assert body["error"]["message"] == "Invalid parameters"
        assert body["error"]["type"] == "api_error"

    def test_falls_back_to_text_on_non_json(self):
        response = httpx.Response(
            status_code=500,
            text="Internal Server Error",
        )
        response._request = httpx.Request("POST", "http://test")
        exc = httpx.HTTPStatusError(
            message="Server Error",
            request=response._request,
            response=response,
        )
        resp = _http_status_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 500
        assert body["error"]["message"] == "Internal Server Error"

    def test_falls_back_to_str_exc_when_no_message_key(self):
        response = httpx.Response(
            status_code=503,
            json={"detail": "Service unavailable"},
        )
        response._request = httpx.Request("POST", "http://test")
        exc = httpx.HTTPStatusError(
            message="Unavailable",
            request=response._request,
            response=response,
        )
        resp = _http_status_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 503
        # Falls back to str(exc) since error.message is missing
        assert "Unavailable" in body["error"]["message"]

    def test_preserves_status_code(self):
        response = httpx.Response(
            status_code=429,
            json={"error": {"message": "Rate limited"}},
        )
        response._request = httpx.Request("POST", "http://test")
        exc = httpx.HTTPStatusError(
            message="Too Many",
            request=response._request,
            response=response,
        )
        resp = _http_status_error_handler(_dummy_request(), exc)
        assert resp.status_code == 429


class TestHttpxErrorHandler:
    def test_generic_httpx_error_returns_502(self):
        exc = httpx.ConnectError("Connection refused")
        resp = _httpx_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 502
        assert body["error"]["type"] == "api_error"
        assert "Connection refused" in body["error"]["message"]

    def test_timeout_error_returns_502(self):
        exc = httpx.ReadTimeout("Read timed out")
        resp = _httpx_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 502
        assert "Read timed out" in body["error"]["message"]


def _parse(resp):
    import json

    return json.loads(resp.body)
