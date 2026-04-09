"""Tests for Responses API streaming → Chat Completions SSE translation."""

import json
import typing as t

from openai.types.responses import Response
from openai.types.responses import ResponseCompletedEvent
from openai.types.responses import ResponseCreatedEvent
from openai.types.responses import ResponseFunctionCallArgumentsDeltaEvent
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses import ResponseOutputItemAddedEvent
from openai.types.responses import ResponseOutputMessage
from openai.types.responses import ResponseTextDeltaEvent
from openai.types.responses import ResponseUsage

from goose_proxy.translators.streaming import translate_stream


def _make_base_response(response_id="resp_1", status="in_progress", output=None, usage=None):
    return Response(
        id=response_id,
        created_at=1700000000,
        model="rhel-lightspeed/vertex",
        object="response",
        output=output or [],
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status=status,
        usage=usage,
    )


def _make_usage():
    return ResponseUsage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        input_tokens_details={"cached_tokens": 0},
        output_tokens_details={"reasoning_tokens": 0},
    )


def _make_text_delta(delta, item_id="m1", output_index=0, sequence_number=1):
    return ResponseTextDeltaEvent(
        content_index=0,
        delta=delta,
        item_id=item_id,
        output_index=output_index,
        sequence_number=sequence_number,
        type="response.output_text.delta",
        logprobs=[],
    )


def _parse_sse_line(line: str) -> t.Any:
    """Parse a single SSE data line into a dict or raw string."""
    assert line.startswith("data: ")
    payload = line.removeprefix("data: ").strip()
    if payload == "[DONE]":
        return "[DONE]"
    return json.loads(payload)


async def _collect_chunks(events, model="rhel-lightspeed/vertex"):
    """Run translate_stream and collect all SSE lines."""

    async def event_iter():
        for e in events:
            yield e

    chunks = []
    async for line in translate_stream(event_iter(), model):
        chunks.append(line)
    return chunks


# --- Text streaming ---


class TestTextStreaming:
    async def test_initial_role_chunk(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[0])
        assert data["choices"][0]["delta"] == {"role": "assistant"}

    async def test_text_delta_chunks(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hello"),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[1])
        assert data["choices"][0]["delta"] == {"content": "Hello"}

    async def test_multiple_text_deltas(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hel", sequence_number=1),
            _make_text_delta("lo!", sequence_number=2),
        ]
        chunks = await _collect_chunks(events)
        # role chunk + 2 text chunks + [DONE]
        assert _parse_sse_line(chunks[1])["choices"][0]["delta"]["content"] == "Hel"
        assert _parse_sse_line(chunks[2])["choices"][0]["delta"]["content"] == "lo!"

    async def test_empty_text_delta(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta(""),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[1])
        assert data["choices"][0]["delta"]["content"] == ""


# --- Tool call streaming ---


class TestToolCallStreaming:
    async def test_function_call_added(self):
        fc = ResponseFunctionToolCall(
            arguments="",
            call_id="call_1",
            name="get_weather",
            type="function_call",
            id="fc_1",
            status="in_progress",
        )
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseOutputItemAddedEvent(
                item=fc,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[1])
        tc = data["choices"][0]["delta"]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_weather"
        assert tc["function"]["arguments"] == ""
        assert tc["index"] == 0

    async def test_function_call_arguments_delta(self):
        fc = ResponseFunctionToolCall(
            arguments="",
            call_id="call_1",
            name="fn",
            type="function_call",
            id="fc_1",
            status="in_progress",
        )
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseOutputItemAddedEvent(
                item=fc,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            ),
            ResponseFunctionCallArgumentsDeltaEvent(
                delta='{"loc',
                item_id="fc_1",
                output_index=0,
                sequence_number=2,
                type="response.function_call_arguments.delta",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[2])
        tc = data["choices"][0]["delta"]["tool_calls"][0]
        assert tc["function"]["arguments"] == '{"loc'
        assert tc["index"] == 0

    async def test_multiple_function_calls_indexed(self):
        fc1 = ResponseFunctionToolCall(
            arguments="",
            call_id="call_1",
            name="fn1",
            type="function_call",
            id="fc_1",
            status="in_progress",
        )
        fc2 = ResponseFunctionToolCall(
            arguments="",
            call_id="call_2",
            name="fn2",
            type="function_call",
            id="fc_2",
            status="in_progress",
        )
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseOutputItemAddedEvent(
                item=fc1,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            ),
            ResponseOutputItemAddedEvent(
                item=fc2,
                output_index=1,
                sequence_number=2,
                type="response.output_item.added",
            ),
        ]
        chunks = await _collect_chunks(events)
        tc1 = _parse_sse_line(chunks[1])["choices"][0]["delta"]["tool_calls"][0]
        tc2 = _parse_sse_line(chunks[2])["choices"][0]["delta"]["tool_calls"][0]
        assert tc1["index"] == 0
        assert tc2["index"] == 1

    async def test_function_call_then_text(self):
        """Mixed tool and text streaming in sequence."""
        fc = ResponseFunctionToolCall(
            arguments="",
            call_id="call_1",
            name="fn",
            type="function_call",
            id="fc_1",
            status="in_progress",
        )
        msg = ResponseOutputMessage(
            id="msg_1",
            content=[],
            role="assistant",
            status="in_progress",
            type="message",
        )
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseOutputItemAddedEvent(
                item=fc,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            ),
            ResponseOutputItemAddedEvent(
                item=msg,
                output_index=1,
                sequence_number=2,
                type="response.output_item.added",
            ),
            _make_text_delta("Hi", item_id="msg_1", output_index=1, sequence_number=3),
        ]
        chunks = await _collect_chunks(events)
        # role, tool_call, text, [DONE]
        # (message added event doesn't emit a new chunk when role already sent)
        tc_data = _parse_sse_line(chunks[1])
        assert "tool_calls" in tc_data["choices"][0]["delta"]
        text_data = _parse_sse_line(chunks[2])
        assert text_data["choices"][0]["delta"]["content"] == "Hi"


# --- Stream lifecycle ---


class TestStreamLifecycle:
    async def test_stream_starts_with_role(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[0])
        assert data["choices"][0]["delta"]["role"] == "assistant"

    async def test_stream_ends_with_done(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseCompletedEvent(
                response=_make_base_response(status="completed", usage=_make_usage()),
                sequence_number=1,
                type="response.completed",
            ),
        ]
        chunks = await _collect_chunks(events)
        assert chunks[-1] == "data: [DONE]\n\n"

    async def test_finish_reason_stop_in_final(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hi"),
            ResponseCompletedEvent(
                response=_make_base_response(status="completed", usage=_make_usage()),
                sequence_number=2,
                type="response.completed",
            ),
        ]
        chunks = await _collect_chunks(events)
        # Last data chunk before [DONE]
        data = _parse_sse_line(chunks[-2])
        assert data["choices"][0]["finish_reason"] == "stop"

    async def test_finish_reason_tool_calls_in_final(self):
        fc = ResponseFunctionToolCall(
            arguments="",
            call_id="call_1",
            name="fn",
            type="function_call",
            id="fc_1",
            status="in_progress",
        )
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseOutputItemAddedEvent(
                item=fc,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            ),
            ResponseCompletedEvent(
                response=_make_base_response(status="completed", usage=_make_usage()),
                sequence_number=2,
                type="response.completed",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[-2])
        assert data["choices"][0]["finish_reason"] == "tool_calls"

    async def test_finish_reason_length_when_incomplete(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Partial"),
            ResponseCompletedEvent(
                response=_make_base_response(status="incomplete", usage=_make_usage()),
                sequence_number=2,
                type="response.completed",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[-2])
        assert data["choices"][0]["finish_reason"] == "length"

    async def test_usage_in_completed_event(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseCompletedEvent(
                response=_make_base_response(status="completed", usage=_make_usage()),
                sequence_number=1,
                type="response.completed",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[-2])
        assert data["usage"]["prompt_tokens"] == 10
        assert data["usage"]["completion_tokens"] == 5
        assert data["usage"]["total_tokens"] == 15


# --- SSE format ---


class TestSSEFormat:
    async def test_chunk_format(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]
        chunks = await _collect_chunks(events)
        for chunk in chunks:
            assert chunk.startswith("data: ")
            assert chunk.endswith("\n\n")

    async def test_chunk_json_valid(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hi"),
        ]
        chunks = await _collect_chunks(events)
        for chunk in chunks:
            parsed = _parse_sse_line(chunk)
            if parsed == "[DONE]":
                continue
            assert isinstance(parsed, dict)

    async def test_chunk_object_type(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]
        chunks = await _collect_chunks(events)
        data = _parse_sse_line(chunks[0])
        assert data["object"] == "chat.completion.chunk"

    async def test_chunk_model_preserved(self):
        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]
        chunks = await _collect_chunks(events, model="my-model")
        data = _parse_sse_line(chunks[0])
        assert data["model"] == "my-model"


# --- Edge cases ---


class TestEdgeCases:
    async def test_unknown_event_ignored(self):
        """Events we don't handle should be silently skipped."""

        class UnknownEvent:
            type = "response.unknown_event"

        events = [
            ResponseCreatedEvent(
                response=_make_base_response(),
                sequence_number=0,
                type="response.created",
            ),
            UnknownEvent(),
            ResponseCompletedEvent(
                response=_make_base_response(status="completed", usage=_make_usage()),
                sequence_number=2,
                type="response.completed",
            ),
        ]
        chunks = await _collect_chunks(events)
        # Should still get: role chunk, completed chunk, [DONE]
        assert len(chunks) == 3

    async def test_empty_stream(self):
        """Stream with only completed event produces minimal output."""
        events = [
            ResponseCompletedEvent(
                response=_make_base_response(status="completed", usage=_make_usage()),
                sequence_number=0,
                type="response.completed",
            ),
        ]
        chunks = await _collect_chunks(events)
        # completed chunk + [DONE]
        assert len(chunks) == 2
        assert chunks[-1] == "data: [DONE]\n\n"
