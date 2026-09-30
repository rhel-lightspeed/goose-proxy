"""Routes for the /v1 API prefix."""

import logging

import httpx
import openai

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import Response
from fastapi.responses import StreamingResponse
from openai.pagination import SyncPage
from openai.types import Model

from goose_proxy.config import get_settings
from goose_proxy.exceptions import CertificateInitializationError


logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/v1")


async def _strip_authorization(request: httpx.Request) -> None:
    """Remove the Authorization header before the request is sent.

    The OpenAI SDK always injects 'Authorization: Bearer <api_key>' regardless
    of the api_key value. The backend authenticates via mTLS (client certificate),
    so the header must be absent — an unexpected Bearer token causes a 401.

    Must be async: httpx.AsyncClient awaits all event hook callables.
    """
    request.headers.pop("authorization", None)


def _build_client() -> openai.AsyncOpenAI:
    """Build an AsyncOpenAI client with mTLS configured via an httpx transport.

    Raises CertificateInitializationError when the RHSM certificates cannot be loaded.
    """
    settings = get_settings()
    backend = settings.backend

    if not backend.auth.cert_file.exists() or not backend.auth.key_file.exists():
        raise CertificateInitializationError()

    certs = str(backend.auth.cert_file), str(backend.auth.key_file)
    return openai.AsyncOpenAI(
        base_url=backend.endpoint,
        timeout=backend.timeout,
        api_key="nothing-to-see-here",
        http_client=openai.DefaultAsyncHttpxClient(
            cert=certs,
            proxy=backend.proxy or None,
            event_hooks={
                "request": [_strip_authorization],
            },
        ),
    )


async def _iter_raw_stream(content, ctx, client):
    """Yield raw bytes from an already-opened streaming response.

    The context has already been entered (__aenter__ called) by the route handler
    before headers are committed to the client. This generator owns cleanup via
    __aexit__ once iteration is complete.
    """
    try:
        async for chunk in content.iter_bytes():
            yield chunk
    finally:
        await ctx.__aexit__(None, None, None)
        await client.close()


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

    if body.get("stream"):
        # Enter the stream here — before returning StreamingResponse — so that any
        # connection error surfaces while exception handlers can still catch it
        # (i.e. before HTTP response headers are committed to the client).
        # _iter_raw_stream takes ownership of both ctx and client cleanup.
        ctx = client.responses.with_streaming_response.create(**body)
        content = await ctx.__aenter__()
        return StreamingResponse(_iter_raw_stream(content, ctx, client), media_type="text/event-stream")

    async with client:
        raw = await client.responses.with_raw_response.create(**body)
        return Response(content=raw.content, media_type="application/json")


@router.get("/models")
async def list_models(_: Request) -> SyncPage[Model]:
    """Return a fixed model list.

    Always returns 'RHEL-command-line-assistant' to hide the real backend model
    from the client.
    """
    return SyncPage(
        object="list",
        data=[Model(id="RHEL-command-line-assistant", created=0, object="model", owned_by="command-line-assistant")],
    )
