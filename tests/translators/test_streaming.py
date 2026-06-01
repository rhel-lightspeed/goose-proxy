import asyncio
import json
import typing as t

import pytest

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


@pytest.fixture
def base_response():
    return _make_base_response


@pytest.fixture
def response_usage():
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


@pytest.fixture
def parse_sse_line():
    def _parse_sse_line(line: str) -> t.Any:
        assert line.startswith("data: ")
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            return "[DONE]"

        return json.loads(payload)

    return _parse_sse_line


@pytest.fixture
def collect_chunks():
    def _collect_chunks(events, model="rhel-lightspeed/vertex"):
        async def _run():
            async def _aiter():
                for e in events:
                    yield e

            return [chunk async for chunk in translate_stream(_aiter(), model)]

        return asyncio.run(_run())

    return _collect_chunks


# --- Text streaming ---


class TestTextStreaming:
    def test_initial_role_chunk(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[0])

        assert data["choices"][0]["delta"] == {"role": "assistant"}

    def test_text_delta_chunks(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hello"),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[1])

        assert data["choices"][0]["delta"] == {"content": "Hello"}

    def test_multiple_text_deltas(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hel", sequence_number=1),
            _make_text_delta("lo!", sequence_number=2),
        ]

        chunks = collect_chunks(events)

        assert parse_sse_line(chunks[1])["choices"][0]["delta"]["content"] == "Hel"
        assert parse_sse_line(chunks[2])["choices"][0]["delta"]["content"] == "lo!"

    def test_empty_text_delta(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta(""),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[1])

        assert data["choices"][0]["delta"]["content"] == ""


# --- Tool call streaming ---


class TestToolCallStreaming:
    def test_function_call_added(self, base_response, collect_chunks, parse_sse_line):
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
                response=base_response(),
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

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[1])
        tc = data["choices"][0]["delta"]["tool_calls"][0]

        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_weather"
        assert tc["function"]["arguments"] == ""
        assert tc["index"] == 0

    def test_function_call_arguments_delta(self, base_response, collect_chunks, parse_sse_line):
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
                response=base_response(),
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

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[2])
        tc = data["choices"][0]["delta"]["tool_calls"][0]

        assert tc["function"]["arguments"] == '{"loc'
        assert tc["index"] == 0

    def test_multiple_function_calls_indexed(self, base_response, collect_chunks, parse_sse_line):
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
                response=base_response(),
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

        chunks = collect_chunks(events)
        tc1 = parse_sse_line(chunks[1])["choices"][0]["delta"]["tool_calls"][0]
        tc2 = parse_sse_line(chunks[2])["choices"][0]["delta"]["tool_calls"][0]

        assert tc1["index"] == 0
        assert tc2["index"] == 1

    def test_function_call_then_text(self, base_response, collect_chunks, parse_sse_line):
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
                response=base_response(),
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

        chunks = collect_chunks(events)
        tc_data = parse_sse_line(chunks[1])
        text_data = parse_sse_line(chunks[2])

        # role, tool_call, text, [DONE]
        # (message added event doesn't emit a new chunk when role already sent)
        assert "tool_calls" in tc_data["choices"][0]["delta"]
        assert text_data["choices"][0]["delta"]["content"] == "Hi"


# --- Stream lifecycle ---


class TestStreamLifecycle:
    def test_stream_starts_with_role(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[0])

        assert data["choices"][0]["delta"]["role"] == "assistant"

    def test_stream_ends_with_done(self, base_response, response_usage, collect_chunks):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseCompletedEvent(
                response=base_response(status="completed", usage=response_usage),
                sequence_number=1,
                type="response.completed",
            ),
        ]

        chunks = collect_chunks(events)

        assert chunks[-1] == "data: [DONE]\n\n"

    def test_finish_reason_stop_in_final(self, base_response, response_usage, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hi"),
            ResponseCompletedEvent(
                response=base_response(status="completed", usage=response_usage),
                sequence_number=2,
                type="response.completed",
            ),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[-2])

        assert data["choices"][0]["finish_reason"] == "stop"

    def test_finish_reason_tool_calls_in_final(self, base_response, response_usage, collect_chunks, parse_sse_line):
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
                response=base_response(),
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
                response=base_response(status="completed", usage=response_usage),
                sequence_number=2,
                type="response.completed",
            ),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[-2])

        assert data["choices"][0]["finish_reason"] == "tool_calls"

    def test_finish_reason_length_when_incomplete(self, base_response, response_usage, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Partial"),
            ResponseCompletedEvent(
                response=base_response(status="incomplete", usage=response_usage),
                sequence_number=2,
                type="response.completed",
            ),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[-2])

        assert data["choices"][0]["finish_reason"] == "length"

    def test_usage_in_completed_event(self, base_response, response_usage, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            ResponseCompletedEvent(
                response=base_response(status="completed", usage=response_usage),
                sequence_number=1,
                type="response.completed",
            ),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[-2])

        assert data["usage"]["prompt_tokens"] == 10
        assert data["usage"]["completion_tokens"] == 5
        assert data["usage"]["total_tokens"] == 15


# --- SSE format ---


class TestSSEFormat:
    def test_chunk_format(self, base_response, collect_chunks):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]

        chunks = collect_chunks(events)

        for chunk in chunks:
            assert chunk.startswith("data: ")
            assert chunk.endswith("\n\n")

    def test_chunk_json_valid(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            _make_text_delta("Hi"),
        ]

        chunks = collect_chunks(events)

        for chunk in chunks:
            parsed = parse_sse_line(chunk)
            if parsed == "[DONE]":
                continue
            assert isinstance(parsed, dict)

    def test_chunk_object_type(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]

        chunks = collect_chunks(events)
        data = parse_sse_line(chunks[0])

        assert data["object"] == "chat.completion.chunk"

    def test_chunk_model_preserved(self, base_response, collect_chunks, parse_sse_line):
        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
        ]

        chunks = collect_chunks(events, model="my-model")
        data = parse_sse_line(chunks[0])

        assert data["model"] == "my-model"


# --- Edge cases ---


class TestEdgeCases:
    def test_unknown_event_ignored(self, base_response, response_usage, collect_chunks):
        class UnknownEvent:
            type = "response.unknown_event"

        events = [
            ResponseCreatedEvent(
                response=base_response(),
                sequence_number=0,
                type="response.created",
            ),
            UnknownEvent(),
            ResponseCompletedEvent(
                response=base_response(status="completed", usage=response_usage),
                sequence_number=2,
                type="response.completed",
            ),
        ]

        chunks = collect_chunks(events)

        # Should still get: role chunk, completed chunk, [DONE]
        assert len(chunks) == 3

        """Stream with only completed event produces minimal output."""

    def test_empty_stream(self, base_response, response_usage, collect_chunks):
        events = [
            ResponseCompletedEvent(
                response=base_response(status="completed", usage=response_usage),
                sequence_number=0,
                type="response.completed",
            ),
        ]

        chunks = collect_chunks(events)

        # completed chunk + [DONE]
        assert len(chunks) == 2
        assert chunks[-1] == "data: [DONE]\n\n"
