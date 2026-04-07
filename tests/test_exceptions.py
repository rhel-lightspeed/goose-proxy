import json

from unittest.mock import MagicMock
from unittest.mock import patch

import httpx

from goose_proxy.exceptions import _http_status_error_handler
from goose_proxy.exceptions import _httpx_error_handler
from goose_proxy.exceptions import _openai_error_response


def _parse(resp):
    return json.loads(resp.get_data(as_text=True))


class TestOpenaiErrorResponse:
    def test_4xx_builds_correct_response(self):
        resp = _openai_error_response(400, "Bad request body", "invalid_request_error")

        assert resp.status_code == 400
        body = _parse(resp)
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["message"] == "Bad request body"
        assert body["error"]["code"] == 400

    def test_500_builds_server_error(self):
        resp = _openai_error_response(500, "Internal error", "server_error")

        body = _parse(resp)
        assert resp.status_code == 500
        assert body["error"]["type"] == "server_error"
        assert body["error"]["message"] == "Internal error"


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

        resp = _http_status_error_handler(exc)

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

        resp = _http_status_error_handler(exc)

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

        resp = _http_status_error_handler(exc)

        body = _parse(resp)
        assert resp.status_code == 503
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

        resp = _http_status_error_handler(exc)

        assert resp.status_code == 429


class TestHttpxErrorHandler:
    def test_generic_httpx_error_returns_502(self):
        exc = httpx.ConnectError("Connection refused")

        resp = _httpx_error_handler(exc)

        body = _parse(resp)
        assert resp.status_code == 502
        assert body["error"]["type"] == "api_error"
        assert "Connection refused" in body["error"]["message"]

    def test_timeout_error_returns_502(self):
        exc = httpx.ReadTimeout("Read timed out")

        resp = _httpx_error_handler(exc)

        body = _parse(resp)
        assert resp.status_code == 502
        assert "Read timed out" in body["error"]["message"]


class TestIntegration:
    def test_error_handler_registered_on_app(self):
        from goose_proxy.app import create_app

        app = create_app()
        app.config["TESTING"] = True
        app.config["http_client"] = MagicMock(spec=httpx.Client)

        with app.test_client() as client:
            with patch(
                "goose_proxy.routers.v1.create_response",
                side_effect=httpx.ConnectError("Connection refused"),
            ):
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "test",
                        "messages": [{"role": "user", "content": "Hi"}],
                    },
                )

        assert resp.status_code == 502
        body = resp.get_json()
        assert body["error"]["type"] == "api_error"
