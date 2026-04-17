import io
import json
import urllib.error

from unittest.mock import MagicMock

import pytest

from fastapi import HTTPException

from goose_proxy.exceptions import _http_error_handler
from goose_proxy.exceptions import _http_exception_handler
from goose_proxy.exceptions import _url_error_handler


def _dummy_request():
    return MagicMock()


@pytest.fixture
def make_http_error():
    def _make_http_error(code, body):
        fp = io.BytesIO(body.encode())

        return urllib.error.HTTPError(
            url="http://test/responses",
            code=code,
            msg="",
            hdrs=None,
            fp=fp,
        )

    return _make_http_error


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


class TestHttpErrorHandler:
    def test_extracts_message_from_json_error(self, make_http_error):
        exc = make_http_error(422, '{"error": {"message": "Invalid parameters"}}')

        resp = _http_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 422
        assert body["error"]["message"] == "Invalid parameters"
        assert body["error"]["type"] == "api_error"

    def test_falls_back_to_text_on_non_json(self, make_http_error):
        exc = make_http_error(500, "Internal Server Error")

        resp = _http_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 500
        assert body["error"]["message"] == "Internal Server Error"

    def test_falls_back_to_str_exc_when_no_message_key(self, make_http_error):
        exc = make_http_error(503, '{"detail": "Service unavailable"}')

        resp = _http_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 503
        assert "503" in body["error"]["message"]

    def test_preserves_status_code(self, make_http_error):
        exc = make_http_error(429, '{"error": {"message": "Rate limited"}}')

        resp = _http_error_handler(_dummy_request(), exc)

        assert resp.status_code == 429


class TestUrlErrorHandler:
    def test_connection_error_returns_502(self):
        exc = urllib.error.URLError("Connection refused")

        resp = _url_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 502
        assert body["error"]["type"] == "api_error"
        assert "Connection refused" in body["error"]["message"]

    def test_timeout_error_returns_502(self):
        exc = urllib.error.URLError("Read timed out")

        resp = _url_error_handler(_dummy_request(), exc)
        body = json.loads(resp.body)

        assert resp.status_code == 502
        assert "Read timed out" in body["error"]["message"]
