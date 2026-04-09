import json

from unittest.mock import MagicMock

import httpx
import openai

from fastapi import HTTPException

from goose_proxy.exceptions import _api_connection_error_handler
from goose_proxy.exceptions import _api_status_error_handler
from goose_proxy.exceptions import _cert_error_handler
from goose_proxy.exceptions import _http_exception_handler
from goose_proxy.exceptions import CertificateInitializationError


def _dummy_request():
    return MagicMock()


def _parse(resp):
    return json.loads(resp.body)


class TestHttpExceptionHandler:
    def test_4xx_returns_invalid_request_error(self):
        exc = HTTPException(status_code=400, detail="Bad request body")

        resp = _http_exception_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 400
        assert resp.body is not None
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


class TestApiStatusErrorHandler:
    def test_extracts_message_from_json_error(self):
        response = httpx.Response(
            status_code=422,
            json={"error": {"message": "Invalid parameters"}},
            request=httpx.Request("POST", "http://test"),
        )
        exc = openai.APIStatusError(
            message="Unprocessable",
            response=response,
            body={"error": {"message": "Invalid parameters"}},
        )
        resp = _api_status_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 422
        assert body["error"]["message"] == "Invalid parameters"
        assert body["error"]["type"] == "api_error"

    def test_falls_back_to_str_on_no_body(self):
        response = httpx.Response(
            status_code=500,
            text="Internal Server Error",
            request=httpx.Request("POST", "http://test"),
        )
        exc = openai.APIStatusError(
            message="Server Error",
            response=response,
            body=None,
        )
        resp = _api_status_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 500
        assert "Server Error" in body["error"]["message"]

    def test_falls_back_to_str_exc_when_no_message_key(self):
        response = httpx.Response(
            status_code=503,
            json={"detail": "Service unavailable"},
            request=httpx.Request("POST", "http://test"),
        )
        exc = openai.APIStatusError(
            message="Unavailable",
            response=response,
            body={"detail": "Service unavailable"},
        )
        resp = _api_status_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 503
        # Falls back to str(exc) since error.message is missing
        assert "Unavailable" in body["error"]["message"]

    def test_preserves_status_code(self):
        response = httpx.Response(
            status_code=429,
            json={"error": {"message": "Rate limited"}},
            request=httpx.Request("POST", "http://test"),
        )
        exc = openai.APIStatusError(
            message="Too Many",
            response=response,
            body={"error": {"message": "Rate limited"}},
        )
        resp = _api_status_error_handler(_dummy_request(), exc)
        assert resp.status_code == 429


class TestApiConnectionErrorHandler:
    def test_connection_error_returns_502(self):
        exc = openai.APIConnectionError(request=httpx.Request("POST", "http://test"))
        resp = _api_connection_error_handler(_dummy_request(), exc)
        body = _parse(resp)
        assert resp.status_code == 502
        assert body["error"]["type"] == "api_error"

    def test_timeout_error_returns_502(self):
        exc = openai.APITimeoutError(request=httpx.Request("POST", "http://test"))
        resp = _api_connection_error_handler(_dummy_request(), exc)
        assert resp.status_code == 502
        body = _parse(resp)
        assert body["error"]["type"] == "api_error"
        assert body["error"]["code"] == 502


class TestCertErrorHandler:
    def test_cert_init_error_returns_502(self):
        cause = FileNotFoundError("[Errno 2] No such file or directory: '/etc/pki/consumer/cert.pem'")
        exc = CertificateInitializationError()
        exc.__cause__ = cause

        resp = _cert_error_handler(_dummy_request(), exc)
        body = _parse(resp)

        assert resp.status_code == 502
        assert body["error"]["type"] == "server_error"
        assert "System is not registered" in body["error"]["message"]
        assert "subscription-manager register" in body["error"]["message"]
        assert "/etc/pki" not in body["error"]["message"]
