"""Routes for the /v1 API prefix."""

import contextlib
import json
import logging

from collections.abc import AsyncIterator
from ssl import SSLCertVerificationError

import httpx

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import Response
from fastapi.responses import StreamingResponse

from goose_proxy.config import get_settings
from goose_proxy.exceptions import CertificateInitializationError


logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/v1")


def _build_client() -> httpx.AsyncClient:
    """Build an httpx async client with mTLS configured for the backend.

    Raises CertificateInitializationError when the RHSM certificates cannot be loaded.
    """
    settings = get_settings()
    backend = settings.backend

    certs = str(backend.auth.cert_file), str(backend.auth.key_file)

    try:
        client = httpx.AsyncClient(
            cert=certs,
            proxy=backend.proxy or None,
            timeout=backend.timeout,
        )
    except (FileNotFoundError, SSLCertVerificationError) as ex:
        raise CertificateInitializationError(
            "Failed to initialize client with RHSM certificates. Check your subscription before continuing"
        ) from ex
    except httpx.InvalidURL as ex:
        raise httpx.InvalidURL("Failed to initialize client. Either baseurl or proxy are invalid") from ex

    return client


def _sse_error_event(message: str, error_type: str = "server_error") -> bytes:
    """Format an error as an SSE event the client can parse.

    Follows the OpenAI streaming error convention so clients that understand
    SSE error events can surface a meaningful message instead of treating a
    truncated stream as an opaque failure.
    """
    payload = json.dumps(
        {
            "type": "error",
            "code": error_type,
            "message": message,
        }
    )
    return f"event: error\ndata: {payload}\n\n".encode()


async def _stream_bytes(
    response: httpx.Response,
    stream_ctx: contextlib.AbstractAsyncContextManager[httpx.Response],
    client: httpx.AsyncClient,
) -> AsyncIterator[bytes]:
    """Yield bytes from a validated streaming response.

    If the stream breaks mid-flight (read timeout, connection reset, etc.),
    emits an SSE error event so the client receives a parseable signal instead
    of a silently truncated stream.

    Owns cleanup of both the stream context manager and the HTTP client.
    """
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    except (httpx.RequestError, httpx.HTTPStatusError, httpx.ResponseNotRead) as exc:
        logger.warning("Mid-stream error from backend: %s", exc)
        yield _sse_error_event(f"Stream interrupted: {exc}")
    finally:
        await stream_ctx.__aexit__(None, None, None)
        await client.aclose()


@router.post("/responses")
async def responses(request: Request):
    """Forward a Responses API request to the lightspeed-stack backend.

    The request body is passed through verbatim. The only transformation applied
    is the injection of the mTLS client certificate for backend authentication.
    """
    body = await request.json()

    # We remove the model from the request body to avoid sending it to the backend,
    # as the backend will automatically pick the model for us.
    body["model"] = ""

    client = _build_client()
    settings = get_settings()
    url = f"{settings.backend.endpoint}/responses"

    if not body.get("stream"):
        async with client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            return Response(content=response.content, media_type="application/json")

    # Streaming path: eagerly connect and validate the backend response
    # *before* constructing StreamingResponse. This ensures that pre-stream
    # errors (4xx/5xx, connection failures) surface as proper JSON error
    # responses instead of broken 200s with no body.
    await client.__aenter__()
    stream_ctx = client.stream("POST", url, json=body)

    try:
        response = await stream_ctx.__aenter__()
        # Only read the body on errors — streaming responses don't eagerly
        # load content, and the exception handler needs access to
        # exc.response.text / .json() for the error message.  On success
        # we must leave the body unread so _stream_bytes can iterate it.
        if response.is_error:
            await response.aread()
            response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError):
        try:
            await stream_ctx.__aexit__(None, None, None)
        except (httpx.HTTPStatusError, httpx.RequestError):
            pass
        await client.aclose()
        raise

    # Connection is healthy and status is 2xx — safe to commit 200 headers.
    # _stream_bytes owns cleanup of stream_ctx and client from here on.
    return StreamingResponse(
        _stream_bytes(response, stream_ctx, client),
        media_type="text/event-stream",
    )


@router.get("/models")
async def list_models(_: Request) -> dict:
    """Return a fixed model list.

    Always returns 'RHEL-command-line-assistant' to hide the real backend model
    from the client.
    """
    return {
        "object": "list",
        "data": [
            {"id": "RHEL-command-line-assistant", "created": 0, "object": "model", "owned_by": "command-line-assistant"}
        ],
    }
