"""Tests for the timeout middleware."""

import asyncio
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route

from goose_proxy.middleware import TimeoutMiddleware


def _make_app(handler, timeout: int | float = 5):
    """Create a minimal Starlette app with TimeoutMiddleware."""
    app = Starlette(routes=[Route("/", handler)])
    mock_settings = MagicMock()
    mock_settings.backend.timeout = timeout

    wrapped = TimeoutMiddleware(app)
    # Patch get_settings for the middleware
    return wrapped, mock_settings


class TestTimeoutMiddleware:
    def test_successful_request_passes_through(self):
        async def handler(request):
            return PlainTextResponse("OK")

        wrapped, mock_settings = _make_app(handler, timeout=5)
        with patch("goose_proxy.middleware.get_settings", return_value=mock_settings):
            client = TestClient(wrapped)
            resp = client.get("/")
        assert resp.status_code == 200
        assert resp.text == "OK"

    def test_slow_response_returns_504(self):
        async def handler(request):
            await asyncio.sleep(10)
            return PlainTextResponse("Too late")

        wrapped, mock_settings = _make_app(handler, timeout=0.1)
        with patch("goose_proxy.middleware.get_settings", return_value=mock_settings):
            client = TestClient(wrapped)
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

    def test_streaming_response_not_cut_short(self):
        """Once headers are sent, the middleware should not enforce a timeout."""

        async def handler(request):
            async def generate():
                yield "chunk1"
                await asyncio.sleep(0.2)
                yield "chunk2"

            return StreamingResponse(generate(), media_type="text/plain")

        wrapped, mock_settings = _make_app(handler, timeout=0.1)
        with patch("goose_proxy.middleware.get_settings", return_value=mock_settings):
            client = TestClient(wrapped)
            resp = client.get("/")
        # The response should complete successfully since headers were sent quickly
        assert resp.status_code == 200
        assert "chunk1" in resp.text
        assert "chunk2" in resp.text

    def test_app_error_propagates(self):
        async def handler(request):
            raise ValueError("Something went wrong")

        wrapped, mock_settings = _make_app(handler, timeout=5)
        with patch("goose_proxy.middleware.get_settings", return_value=mock_settings):
            client = TestClient(wrapped, raise_server_exceptions=False)
            resp = client.get("/")
        assert resp.status_code == 500
