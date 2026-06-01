"""Translate Responses API streaming events to Chat Completions SSE chunks."""

import json
import time
import typing as t

from collections.abc import AsyncIterator

from openai.types.responses import ResponseCompletedEvent
from openai.types.responses import ResponseCreatedEvent
from openai.types.responses import ResponseFunctionCallArgumentsDeltaEvent
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses import ResponseOutputItemAddedEvent
from openai.types.responses import ResponseOutputMessage
from openai.types.responses import ResponseStreamEvent
from openai.types.responses import ResponseTextDeltaEvent


def _make_chunk(
    request_id: str,
    model: str,
    created: int,
    delta: dict[str, t.Any],
    finish_reason: t.Optional[str] = None,
    usage: t.Optional[t.Dict[str, t.Any]] = None,
) -> str:
    """Build a single SSE line for a Chat Completions chunk."""
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }

    return f"data: {json.dumps(chunk)}\n\n"


def _make_tool_call_delta(index: int, item: ResponseFunctionToolCall) -> dict[str, t.Any]:
    """Build the delta dict for a new tool call announcement."""
    return {
        "tool_calls": [
            {
                "index": index,
                "id": item.call_id,
                "type": "function",
                "function": {
                    "name": item.name,
                    "arguments": "",
                },
            }
        ]
    }


def _make_tool_call_arguments_delta(index: int, arguments: str) -> dict[str, t.Any]:
    """Build the delta dict for incremental tool call arguments."""
    return {
        "tool_calls": [
            {
                "index": index,
                "function": {"arguments": arguments},
            }
        ]
    }


def _determine_finish_reason(event: ResponseCompletedEvent, has_tool_calls: bool) -> str:
    """Determine finish_reason from a completed event."""
    reason = "stop"
    if has_tool_calls:
        reason = "tool_calls"
    if event.response.status == "incomplete":
        reason = "length"

    return reason


def _translate_usage(event: ResponseCompletedEvent) -> t.Optional[dict[str, int]]:
    """Extract usage from a completed event into Chat Completions format."""
    if event.response.usage is None:
        return None

    return {
        "prompt_tokens": event.response.usage.input_tokens,
        "completion_tokens": event.response.usage.output_tokens,
        "total_tokens": event.response.usage.total_tokens,
    }


async def translate_stream(
    stream: AsyncIterator[ResponseStreamEvent],
    model: t.Optional[str],
) -> AsyncIterator[str]:
    """Translate Responses API stream events into Chat Completions SSE lines.

    Args:
        stream: Async iterator of streaming event objects from the backend.
        model: The original model name from the request, or None to use the response model.

    Yields:
        SSE-formatted lines (``data: {...}\\n\\n``), ending with ``data: [DONE]\\n\\n``.
    """
    request_id = ""
    model_name: str = model or ""
    created = int(time.time())
    tool_call_index = -1
    has_tool_calls = False
    sent_role = False

    async for event in stream:
        if isinstance(event, ResponseCreatedEvent):
            request_id = event.response.id
            created = int(event.response.created_at)
            if not model_name:
                model_name = event.response.model

            if not sent_role:
                yield _make_chunk(request_id, model_name, created, {"role": "assistant"})
                sent_role = True

        elif isinstance(event, ResponseTextDeltaEvent):
            yield _make_chunk(request_id, model_name, created, {"content": event.delta})

        elif isinstance(event, ResponseOutputItemAddedEvent):
            if isinstance(event.item, ResponseFunctionToolCall):
                tool_call_index += 1
                has_tool_calls = True
                delta = _make_tool_call_delta(tool_call_index, event.item)
                yield _make_chunk(request_id, model_name, created, delta)
            elif isinstance(event.item, ResponseOutputMessage):
                if not sent_role:
                    yield _make_chunk(request_id, model_name, created, {"role": "assistant"})
                    sent_role = True

        elif isinstance(event, ResponseFunctionCallArgumentsDeltaEvent):
            delta = _make_tool_call_arguments_delta(tool_call_index, event.delta)
            yield _make_chunk(request_id, model_name, created, delta)

        elif isinstance(event, ResponseCompletedEvent):
            finish_reason = _determine_finish_reason(event, has_tool_calls)
            usage = _translate_usage(event)
            yield _make_chunk(
                request_id,
                model_name,
                created,
                {},
                finish_reason=finish_reason,
                usage=usage,
            )

    yield "data: [DONE]\n\n"
