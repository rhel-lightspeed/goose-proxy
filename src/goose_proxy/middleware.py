import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi.responses import JSONResponse

from goose_proxy.config import get_settings


class TimeoutMiddleware:
    """ASGI middleware that enforces a timeout on the backend's initial response.

    The timeout covers the period until the backend starts responding (sends
    headers). Once the response has started, no timeout is enforced — this
    allows streaming responses to run as long as needed.

    Implemented as a pure ASGI middleware to avoid BaseHTTPMiddleware's known
    issues with streaming response buffering.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        timeout = get_settings().backend.timeout
        response_started = asyncio.Event()

        async def send_with_signal(message):
            if message["type"] == "http.response.start":
                response_started.set()
            await send(message)

        coro = self.app(scope, receive, send_with_signal)
        assert asyncio.iscoroutine(coro)
        app_task = asyncio.create_task(coro)

        try:
            await asyncio.wait_for(response_started.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            app_task.cancel()
            try:
                await app_task
            except asyncio.CancelledError:
                pass
            if not response_started.is_set():
                response = JSONResponse(
                    {
                        "error": {
                            "message": "Request timed out while waiting for the backend.",
                            "type": "server_error",
                            "code": 504,
                        }
                    },
                    status_code=504,
                )
                await response(scope, receive, send)
            return

        # Response has started — let it finish without a timeout.
        # Re-raise any exception from the app task.
        await app_task
