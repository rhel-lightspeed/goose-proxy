"""Tests for Responses API → Chat Completions response translation."""

import pytest

from goose_proxy.models.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseUsage,
)
from goose_proxy.translators.response import translate_response


def _make_usage(input_tokens=10, output_tokens=5, total_tokens=15):
    return ResponseUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _make_response(output=None, usage=None, status="completed", response_id="resp_1"):
    return Response(
        id=response_id,
        created_at=1700000000,
        model="rhel-lightspeed/vertex",
        object="response",
        output=output or [],
        status=status,
        usage=usage,
    )


def _make_message_output(text="Hello!", msg_id="msg_1", status="completed"):
    return ResponseOutputMessage(
        id=msg_id,
        content=[ResponseOutputText(annotations=[], text=text, type="output_text")],
        role="assistant",
        status=status,
        type="message",
    )


def _make_function_call_output(
    name="get_weather",
    arguments='{"location": "London"}',
    call_id="call_1",
    fc_id="fc_1",
    status="completed",
):
    return ResponseFunctionToolCall(
        arguments=arguments,
        call_id=call_id,
        name=name,
        type="function_call",
        id=fc_id,
        status=status,
    )


@pytest.fixture
def text_response():
    return _make_response(
        output=[_make_message_output("Hello!")],
        usage=_make_usage(),
    )


@pytest.fixture
def tool_call_response():
    return _make_response(
        output=[
            _make_function_call_output(
                name="get_weather",
                arguments='{"location": "London"}',
                call_id="call_abc",
            )
        ],
        usage=_make_usage(),
    )


@pytest.fixture
def mixed_response():
    return _make_response(
        output=[
            _make_message_output("Let me check the weather."),
            _make_function_call_output(
                name="get_weather",
                arguments='{"location": "London"}',
                call_id="call_abc",
            ),
        ],
        usage=_make_usage(),
    )


@pytest.fixture
def multi_tool_call_response():
    return _make_response(
        output=[
            _make_function_call_output(
                name="get_weather",
                arguments='{"location": "London"}',
                call_id="call_1",
                fc_id="fc_1",
            ),
            _make_function_call_output(
                name="get_weather",
                arguments='{"location": "Paris"}',
                call_id="call_2",
                fc_id="fc_2",
            ),
        ],
        usage=_make_usage(),
    )


@pytest.fixture
def no_usage_response():
    return _make_response(
        output=[_make_message_output("Hello!")],
        usage=None,
    )


@pytest.fixture
def empty_output_response():
    return _make_response(output=[], usage=_make_usage())


@pytest.fixture
def incomplete_response():
    return _make_response(
        output=[_make_message_output("Partial answer...")],
        usage=_make_usage(),
        status="incomplete",
    )


# --- Content extraction ---


class TestContentExtraction:
    def test_simple_text_response(self, text_response):
        result = translate_response(text_response, "m")
        assert result.choices[0].message.content == "Hello!"

    def test_multiple_output_text_parts(self):
        msg = ResponseOutputMessage(
            id="msg_1",
            content=[
                ResponseOutputText(annotations=[], text="Hello ", type="output_text"),
                ResponseOutputText(annotations=[], text="world!", type="output_text"),
            ],
            role="assistant",
            status="completed",
            type="message",
        )
        resp = _make_response(output=[msg], usage=_make_usage())
        result = translate_response(resp, "m")
        assert result.choices[0].message.content == "Hello world!"

    def test_empty_content(self):
        msg = ResponseOutputMessage(
            id="msg_1",
            content=[],
            role="assistant",
            status="completed",
            type="message",
        )
        resp = _make_response(output=[msg], usage=_make_usage())
        result = translate_response(resp, "m")
        assert result.choices[0].message.content is None

    def test_response_with_no_output(self, empty_output_response):
        result = translate_response(empty_output_response, "m")
        assert result.choices[0].message.content is None


# --- Tool call mapping ---


class TestToolCallMapping:
    def test_single_tool_call(self, tool_call_response):
        result = translate_response(tool_call_response, "m")
        tc = result.choices[0].message.tool_calls
        assert tc is not None
        assert len(tc) == 1
        assert tc[0].id == "call_abc"
        assert tc[0].function.name == "get_weather"
        assert tc[0].function.arguments == '{"location": "London"}'
        assert tc[0].type == "function"

    def test_multiple_tool_calls(self, multi_tool_call_response):
        result = translate_response(multi_tool_call_response, "m")
        tc = result.choices[0].message.tool_calls
        assert tc is not None
        assert len(tc) == 2
        assert tc[0].id == "call_1"
        assert tc[1].id == "call_2"

    def test_tool_call_arguments_preserved(self):
        args = '{"complex": {"nested": [1, 2, 3]}, "key": "value"}'
        fc = _make_function_call_output(arguments=args, call_id="c1")
        resp = _make_response(output=[fc], usage=_make_usage())
        result = translate_response(resp, "m")
        assert result.choices[0].message.tool_calls[0].function.arguments == args


# --- Mixed output ---


class TestMixedOutput:
    def test_text_and_tool_calls(self, mixed_response):
        result = translate_response(mixed_response, "m")
        msg = result.choices[0].message
        assert msg.content == "Let me check the weather."
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1

    def test_tool_calls_only_no_text(self, tool_call_response):
        result = translate_response(tool_call_response, "m")
        msg = result.choices[0].message
        assert msg.content is None
        assert msg.tool_calls is not None


# --- Finish reason ---


class TestFinishReason:
    def test_finish_reason_stop(self, text_response):
        result = translate_response(text_response, "m")
        assert result.choices[0].finish_reason == "stop"

    def test_finish_reason_tool_calls(self, tool_call_response):
        result = translate_response(tool_call_response, "m")
        assert result.choices[0].finish_reason == "tool_calls"

    def test_finish_reason_length(self, incomplete_response):
        result = translate_response(incomplete_response, "m")
        assert result.choices[0].finish_reason == "length"


# --- Usage mapping ---


class TestUsageMapping:
    def test_usage_tokens_mapped(self, text_response):
        result = translate_response(text_response, "m")
        assert result.usage is not None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5

    def test_usage_total_tokens(self, text_response):
        result = translate_response(text_response, "m")
        assert result.usage.total_tokens == 15

    def test_usage_none(self, no_usage_response):
        result = translate_response(no_usage_response, "m")
        assert result.usage is None


# --- Response metadata ---


class TestResponseMetadata:
    def test_id_from_response(self, text_response):
        result = translate_response(text_response, "m")
        assert result.id == "resp_1"

    def test_created_from_response(self, text_response):
        result = translate_response(text_response, "m")
        assert result.created == 1700000000

    def test_model_uses_original(self, text_response):
        result = translate_response(text_response, "original-model")
        assert result.model == "original-model"

    def test_object_is_chat_completion(self, text_response):
        result = translate_response(text_response, "m")
        assert result.object == "chat.completion"

    def test_single_choice_index_zero(self, text_response):
        result = translate_response(text_response, "m")
        assert len(result.choices) == 1
        assert result.choices[0].index == 0
