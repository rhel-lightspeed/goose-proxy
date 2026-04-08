import json
import logging

from collections.abc import Iterator

import httpx

from flask import Blueprint
from flask import current_app
from flask import request
from flask import Response

from goose_proxy.models.chat import ChatCompletionRequest
from goose_proxy.models.chat import ModelInfo
from goose_proxy.models.chat import ModelsResponse
from goose_proxy.models.responses import parse_stream_event
from goose_proxy.models.responses import Response as ResponsesAPIResponse
from goose_proxy.models.responses import StreamEvent
from goose_proxy.translators import translate_request
from goose_proxy.translators import translate_response
from goose_proxy.translators import translate_stream


logger = logging.getLogger(__name__)

bp = Blueprint("v1", __name__)


def create_response(client: httpx.Client, **params) -> ResponsesAPIResponse:
    resp = client.post("/responses", json=params)
    resp.raise_for_status()
    return ResponsesAPIResponse.model_validate(resp.json())


def stream_response(client: httpx.Client, **params) -> Iterator[StreamEvent]:
    with client.stream(
        "POST",
        "/responses",
        json=params,
    ) as resp:
        if resp.is_error:
            resp.read()
            resp.raise_for_status()

        for line in resp.iter_lines():
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


@bp.post("/chat/completions")
def chat_completions():
    from pydantic import ValidationError

    try:
        data = ChatCompletionRequest.model_validate(request.get_json())
    except ValidationError as exc:
        return Response(
            response=json.dumps({"detail": exc.errors()}),
            status=422,
            content_type="application/json",
        )

    client: httpx.Client = current_app.config["http_client"]
    params = translate_request(data)
    if data.stream:
        stream = stream_response(client, **params)

        def generate():
            for line in translate_stream(stream, data.model):
                yield line

        return Response(generate(), content_type="text/event-stream")

    response = create_response(client, **params)
    result = translate_response(response, data.model)
    return Response(
        response=result.model_dump_json(exclude_none=True),
        status=200,
        content_type="application/json",
    )


@bp.get("/models")
def list_models():
    result = ModelsResponse(
        data=[
            ModelInfo(
                id="rhel-lightspeed/goose",
                owned_by="rhel-lightspeed",
            )
        ]
    )
    return Response(
        response=result.model_dump_json(),
        status=200,
        content_type="application/json",
    )
