import json

import pytest

from goose_proxy.middleware import TimeoutMiddleware


def _make_wsgi_app(handler):
    def app(environ, start_response):
        return handler(environ, start_response)

    return app


class TestTimeoutMiddleware:
    def test_successful_request_passes_through(self):
        def handler(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"OK"]

        wrapped = TimeoutMiddleware(_make_wsgi_app(handler))
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/"}
        status_holder = [None]

        def start_response(status, headers, exc_info=None):
            status_holder[0] = status

        result = wrapped(environ, start_response)

        assert status_holder[0] == "200 OK"
        assert result == [b"OK"]

    def test_timeout_error_returns_504(self):
        def handler(environ, start_response):
            raise TimeoutError("timed out")

        wrapped = TimeoutMiddleware(_make_wsgi_app(handler))
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/"}
        status_holder = [None]

        def start_response(status, headers, exc_info=None):
            status_holder[0] = status

        result = wrapped(environ, start_response)

        assert status_holder[0] == "504 Gateway Timeout"
        body = json.loads(b"".join(result))
        assert body["error"]["type"] == "server_error"
        assert body["error"]["code"] == 504
        assert "timed out" in body["error"]["message"]

    def test_non_timeout_error_propagates(self):
        def handler(environ, start_response):
            raise ValueError("Something went wrong")

        wrapped = TimeoutMiddleware(_make_wsgi_app(handler))
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/"}

        def start_response(status, headers, exc_info=None):
            pass

        with pytest.raises(ValueError, match="Something went wrong"):
            wrapped(environ, start_response)

    def test_streaming_response_passes_through(self):
        def handler(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"chunk1", b"chunk2"]

        wrapped = TimeoutMiddleware(_make_wsgi_app(handler))
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/"}
        status_holder = [None]

        def start_response(status, headers, exc_info=None):
            status_holder[0] = status

        result = wrapped(environ, start_response)

        assert status_holder[0] == "200 OK"
        assert b"chunk1" in result
        assert b"chunk2" in result
