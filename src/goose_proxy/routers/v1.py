import json
import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from goose_proxy.models.chat import ChatCompletionRequest, ModelInfo, ModelsResponse
from goose_proxy.models.responses import Response, StreamEvent, parse_stream_event
from goose_proxy.translators import (
    translate_request,
    translate_response,
    translate_stream,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def create_response(client: httpx.AsyncClient, **params) -> Response:
    """Create a response via the Responses API."""
    resp = await client.post("/responses", json=params)
    resp.raise_for_status()
    return Response.model_validate(resp.json())


async def stream_response(
    client: httpx.AsyncClient, **params
) -> AsyncIterator[StreamEvent]:
    """Stream a response and yield parsed event models."""
    async with client.stream(
        "POST",
        "/responses",
        json=params,
    ) as resp:
        if resp.is_error:
            await resp.aread()
            resp.raise_for_status()

        async for line in resp.aiter_lines():
            line = line.strip()
            if not line or line.startswith("event:"):
                continue
            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed SSE data: %s", payload[:120])
                    continue
                event = parse_stream_event(data)
                if event is not None:
                    yield event


@router.post("/chat/completions", response_model_exclude_none=True)
async def chat_completions(request: Request, data: ChatCompletionRequest):
    client: httpx.AsyncClient = request.app.state.http_client
    params = translate_request(data)
    if data.stream:
        stream = stream_response(client, **params)

        async def generate():
            async for line in translate_stream(stream, data.model):
                yield line

        return StreamingResponse(generate(), media_type="text/event-stream")

    response = await create_response(client, **params)
    return translate_response(response, data.model)


@router.get("/models")
async def list_models(_: Request) -> ModelsResponse:
    """Return fixed model info instead of querying the backend.

    Always returns 'rhel-lightspeed/goose' as the available model.
    This simplifies the proxy by avoiding dynamic model lookups.
    """
    return ModelsResponse(
        data=[
            ModelInfo(
                id="rhel-lightspeed/goose",
                owned_by="rhel-lightspeed",
            )
        ]
    )
