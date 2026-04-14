"""Tests for the timeout middleware."""

import asyncio

from unittest.mock import MagicMock

import pytest

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.responses import StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from goose_proxy.middleware import TimeoutMiddleware


@pytest.fixture
def make_app(monkeypatch):
    """Factory fixture that creates a Starlette app wrapped in TimeoutMiddleware."""

    def _make(handler, timeout=5):
        app = Starlette(routes=[Route("/", handler)])
        mock_settings = MagicMock()
        mock_settings.backend.timeout = timeout
        monkeypatch.setattr("goose_proxy.middleware.get_settings", lambda: mock_settings)
        return TimeoutMiddleware(app)

    return _make


class TestTimeoutMiddleware:
    def test_successful_request_passes_through(self, make_app):
        async def handler(request):
            return PlainTextResponse("OK")

        client = TestClient(make_app(handler, timeout=5))
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.text == "OK"

    def test_slow_response_returns_504(self, make_app):
        async def handler(request):
            await asyncio.sleep(10)
            return PlainTextResponse("Too late")

        client = TestClient(make_app(handler, timeout=0.1))
        resp = client.get("/")
        assert resp.status_code == 504
        body = resp.json()
        assert body["error"]["type"] == "server_error"
        assert body["error"]["code"] == 504
        assert "timed out" in body["error"]["message"]

    async def test_non_http_scope_bypasses_timeout(self):
        """WebSocket and lifespan scopes should pass through without timeout."""
        call_log = []

        async def inner_app(scope, receive, send):
            call_log.append(scope["type"])

        middleware = TimeoutMiddleware(inner_app)
        scope = {"type": "websocket"}
        await middleware(scope, None, None)
        assert call_log == ["websocket"]

    def test_streaming_response_not_cut_short(self, make_app):
        """Once headers are sent, the middleware should not enforce a timeout."""

        async def handler(request):
            async def generate():
                yield "chunk1"
                await asyncio.sleep(0.2)
                yield "chunk2"

            return StreamingResponse(generate(), media_type="text/plain")

        client = TestClient(make_app(handler, timeout=0.1))
        resp = client.get("/")
        assert resp.status_code == 200
        assert "chunk1" in resp.text
        assert "chunk2" in resp.text

    def test_app_error_propagates(self, make_app):
        async def handler(request):
            raise ValueError("Something went wrong")

        client = TestClient(make_app(handler, timeout=5), raise_server_exceptions=False)
        resp = client.get("/")
        assert resp.status_code == 500
