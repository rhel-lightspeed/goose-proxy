import logging

from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from goose_proxy.models.chat import ChatCompletionRequest
from goose_proxy.models.chat import ModelInfo
from goose_proxy.models.chat import ModelsResponse
from goose_proxy.translators import translate_request
from goose_proxy.translators import translate_response
from goose_proxy.translators import translate_stream


logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat/completions", response_model_exclude_none=True)
async def chat_completions(request: Request, data: ChatCompletionRequest):
    client: AsyncOpenAI = request.app.state.openai_client
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
