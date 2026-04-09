import logging
import typing as t

from functools import lru_cache

import httpx

from fastapi import APIRouter
from fastapi import Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from goose_proxy.config import get_settings
from goose_proxy.exceptions import CertificateInitializationError
from goose_proxy.models.chat import ChatCompletionRequest
from goose_proxy.models.chat import ModelInfo
from goose_proxy.models.chat import ModelsResponse
from goose_proxy.translators import translate_request
from goose_proxy.translators import translate_response
from goose_proxy.translators import translate_stream


logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/v1")


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    """Create a cached AsyncOpenAI client configured from settings."""
    settings = get_settings()
    backend = settings.backend
    for cert_path in (backend.auth.cert_file, backend.auth.key_file):
        if not cert_path.exists():
            raise CertificateInitializationError() from FileNotFoundError(f"No such file or directory: '{cert_path}'")

    cert = (str(backend.auth.cert_file), str(backend.auth.key_file))
    http_client = httpx.AsyncClient(
        cert=cert,
        timeout=backend.timeout,
        proxy=backend.proxy or None,
    )
    return AsyncOpenAI(
        base_url=backend.endpoint,
        api_key="",
        http_client=http_client,
    )


@router.post("/chat/completions", response_model_exclude_none=True)
async def chat_completions(
    data: ChatCompletionRequest,
    client: t.Annotated[AsyncOpenAI, Depends(get_openai_client)],
):
    params = translate_request(data)
    if data.stream:
        stream = await client.responses.create(**params)

        async def generate():
            async for line in translate_stream(stream, data.model):
                yield line

        return StreamingResponse(generate(), media_type="text/event-stream")

    response = await client.responses.create(**params)
    return translate_response(response, data.model)


@router.get("/models")
async def list_models() -> ModelsResponse:
    """Return fixed model info instead of querying the backend.

    Always returns 'RHEL-command-line-assistant' as the available model.
    This simplifies the proxy by avoiding dynamic model lookups.
    """
    return ModelsResponse(
        data=[
            ModelInfo(
                id="RHEL-command-line-assistant",
                owned_by="command-line-assistant",
            )
        ]
    )
