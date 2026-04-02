"""Tests for Chat Completions → Responses API request translation."""

import pytest

from goose_proxy.models.chat import (
    ChatCompletionMessageToolCall,
    ChatCompletionRequest,
    ChatMessage,
    Function,
    Tool,
    ToolFunction,
)
from goose_proxy.translators.request import translate_request


@pytest.fixture
def simple_chat_request():
    return ChatCompletionRequest(
        model="rhel-lightspeed/goose",
        messages=[ChatMessage(role="user", content="Hello, world!")],
    )


@pytest.fixture
def chat_request_with_system():
    return ChatCompletionRequest(
        model="rhel-lightspeed/goose",
        messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="What is Python?"),
        ],
    )


@pytest.fixture
def chat_request_with_tools():
    return ChatCompletionRequest(
        model="rhel-lightspeed/goose",
        messages=[ChatMessage(role="user", content="What is the weather?")],
        tools=[
            Tool(
                function=ToolFunction(
                    name="get_weather",
                    description="Get the current weather",
                    parameters={
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                        },
                        "required": ["location"],
                    },
                )
            )
        ],
        tool_choice="auto",
    )


@pytest.fixture
def chat_request_with_tool_results():
    return ChatCompletionRequest(
        model="rhel-lightspeed/goose",
        messages=[
            ChatMessage(role="user", content="What is the weather in London?"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ChatCompletionMessageToolCall(
                        id="call_abc123",
                        type="function",
                        function=Function(
                            name="get_weather",
                            arguments='{"location": "London"}',
                        ),
                    )
                ],
            ),
            ChatMessage(
                role="tool",
                tool_call_id="call_abc123",
                content='{"temperature": 15, "condition": "cloudy"}',
            ),
        ],
        tools=[
            Tool(
                function=ToolFunction(
                    name="get_weather",
                    description="Get the current weather",
                    parameters={
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                )
            )
        ],
    )


@pytest.fixture
def full_conversation_request():
    return ChatCompletionRequest(
        model="rhel-lightspeed/goose",
        messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="What is the weather in London?"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ChatCompletionMessageToolCall(
                        id="call_abc123",
                        type="function",
                        function=Function(
                            name="get_weather",
                            arguments='{"location": "London"}',
                        ),
                    )
                ],
            ),
            ChatMessage(
                role="tool",
                tool_call_id="call_abc123",
                content='{"temperature": 15, "condition": "cloudy"}',
            ),
            ChatMessage(
                role="assistant",
                content="The weather in London is 15C and cloudy.",
            ),
            ChatMessage(role="user", content="And in Paris?"),
        ],
        tools=[
            Tool(
                function=ToolFunction(
                    name="get_weather",
                    description="Get the current weather",
                    parameters={
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"],
                    },
                )
            )
        ],
    )


@pytest.fixture
def streaming_chat_request():
    return ChatCompletionRequest(
        model="rhel-lightspeed/goose",
        messages=[ChatMessage(role="user", content="Hello!")],
        stream=True,
        stream_options={"include_usage": True},
    )


# --- Message translation ---


class TestUserMessages:
    def test_simple_user_message(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert result["input"] == [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello, world!"}],
            }
        ]

    def test_user_message_empty_content(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="")],
        )
        result = translate_request(req)
        assert result["input"][0]["content"][0]["text"] == ""

    def test_user_message_array_content_text_only(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(
                    role="user",
                    content=[{"type": "text", "text": "What is this?"}],
                )
            ],
        )
        result = translate_request(req)
        assert result["input"][0]["content"] == [
            {"type": "input_text", "text": "What is this?"}
        ]

    def test_user_message_array_content_with_image(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "Describe this image"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,abc123"},
                        },
                    ],
                )
            ],
        )
        result = translate_request(req)
        content = result["input"][0]["content"]
        assert len(content) == 2
        assert content[0] == {"type": "input_text", "text": "Describe this image"}
        assert content[1] == {
            "type": "input_image",
            "image_url": "data:image/png;base64,abc123",
        }

    def test_user_message_array_content_none(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content=None)],
        )
        result = translate_request(req)
        assert result["input"][0]["content"] == [{"type": "input_text", "text": ""}]


class TestSystemMessages:
    def test_system_message_to_instructions(self, chat_request_with_system):
        result = translate_request(chat_request_with_system)
        assert result["instructions"] == "You are a helpful assistant."
        # System message should not appear in input
        assert all(item.get("role") != "system" for item in result["input"])

    def test_multiple_system_messages_concatenated(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="system", content="Be helpful."),
                ChatMessage(role="system", content="Be concise."),
                ChatMessage(role="user", content="Hi"),
            ],
        )
        result = translate_request(req)
        assert result["instructions"] == "Be helpful.\n\nBe concise."

    def test_system_messages_interleaved(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="system", content="First."),
                ChatMessage(role="user", content="Hi"),
                ChatMessage(role="system", content="Second."),
                ChatMessage(role="user", content="Hello"),
            ],
        )
        result = translate_request(req)
        assert result["instructions"] == "First.\n\nSecond."
        # Only user messages in input
        assert len(result["input"]) == 2

    def test_no_system_messages(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert "instructions" not in result


class TestAssistantMessages:
    def test_assistant_text_message(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(role="assistant", content="Hello there!"),
            ],
        )
        result = translate_request(req)
        assert result["input"][1] == {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hello there!"}],
        }

    def test_assistant_message_no_content(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(role="assistant", content=None),
            ],
        )
        result = translate_request(req)
        # No content, no tool calls -> no items added for this assistant message
        assert len(result["input"]) == 1

    def test_assistant_with_single_tool_call(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id="call_1",
                            type="function",
                            function=Function(name="fn", arguments='{"a": 1}'),
                        )
                    ],
                ),
            ],
        )
        result = translate_request(req)
        assert result["input"][1] == {
            "type": "function_call",
            "call_id": "call_1",
            "name": "fn",
            "arguments": '{"a": 1}',
        }

    def test_assistant_with_multiple_tool_calls(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id="call_1",
                            type="function",
                            function=Function(name="fn1", arguments="{}"),
                        ),
                        ChatCompletionMessageToolCall(
                            id="call_2",
                            type="function",
                            function=Function(name="fn2", arguments="{}"),
                        ),
                    ],
                ),
            ],
        )
        result = translate_request(req)
        fc_items = [i for i in result["input"] if i.get("type") == "function_call"]
        assert len(fc_items) == 2
        assert fc_items[0]["call_id"] == "call_1"
        assert fc_items[1]["call_id"] == "call_2"

    def test_assistant_with_content_and_tool_calls(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(
                    role="assistant",
                    content="Let me check.",
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id="call_1",
                            type="function",
                            function=Function(name="fn", arguments="{}"),
                        )
                    ],
                ),
            ],
        )
        result = translate_request(req)
        # Should have: user message, assistant message, function_call
        assert len(result["input"]) == 3
        assert result["input"][1]["role"] == "assistant"
        assert result["input"][1]["content"][0]["text"] == "Let me check."
        assert result["input"][2]["type"] == "function_call"


class TestToolMessages:
    def test_tool_message_to_function_call_output(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(
                    role="tool",
                    tool_call_id="call_1",
                    content='{"result": 42}',
                ),
            ],
        )
        result = translate_request(req)
        assert result["input"][1] == {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"result": 42}',
        }

    def test_tool_message_content_preserved(self):
        content = "Some tool output with special chars: <>&"
        req = ChatCompletionRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content="Hi"),
                ChatMessage(role="tool", tool_call_id="c1", content=content),
            ],
        )
        result = translate_request(req)
        assert result["input"][1]["output"] == content


class TestConversationOrder:
    def test_multi_turn_conversation_order(self, full_conversation_request):
        result = translate_request(full_conversation_request)
        input_items = result["input"]
        # user, function_call, function_call_output, assistant, user
        assert input_items[0]["role"] == "user"
        assert input_items[1]["type"] == "function_call"
        assert input_items[2]["type"] == "function_call_output"
        assert input_items[3]["role"] == "assistant"
        assert input_items[4]["role"] == "user"

    def test_multi_turn_with_tool_round_trip(self, chat_request_with_tool_results):
        result = translate_request(chat_request_with_tool_results)
        input_items = result["input"]
        assert input_items[0]["role"] == "user"
        assert input_items[1]["type"] == "function_call"
        assert input_items[1]["call_id"] == "call_abc123"
        assert input_items[2]["type"] == "function_call_output"
        assert input_items[2]["call_id"] == "call_abc123"


# --- Tool translation ---


class TestToolTranslation:
    def test_tools_flattened(self, chat_request_with_tools):
        result = translate_request(chat_request_with_tools)
        tool = result["tools"][0]
        assert tool["type"] == "function"
        assert tool["name"] == "get_weather"
        assert "function" not in tool

    def test_tool_with_description(self, chat_request_with_tools):
        result = translate_request(chat_request_with_tools)
        assert result["tools"][0]["description"] == "Get the current weather"

    def test_tool_with_parameters(self, chat_request_with_tools):
        result = translate_request(chat_request_with_tools)
        params = result["tools"][0]["parameters"]
        assert params["type"] == "object"
        assert "location" in params["properties"]

    def test_tool_without_optional_fields(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            tools=[Tool(function=ToolFunction(name="bare_fn"))],
        )
        result = translate_request(req)
        tool = result["tools"][0]
        assert tool["name"] == "bare_fn"
        assert "description" not in tool
        assert "parameters" not in tool

    def test_multiple_tools(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            tools=[
                Tool(function=ToolFunction(name="fn1", description="First")),
                Tool(function=ToolFunction(name="fn2", description="Second")),
            ],
        )
        result = translate_request(req)
        assert len(result["tools"]) == 2
        assert result["tools"][0]["name"] == "fn1"
        assert result["tools"][1]["name"] == "fn2"

    def test_no_tools(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert "tools" not in result


# --- Tool choice translation ---


class TestToolChoiceTranslation:
    def test_tool_choice_auto(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            tool_choice="auto",
        )
        result = translate_request(req)
        assert result["tool_choice"] == "auto"

    def test_tool_choice_required(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            tool_choice="required",
        )
        result = translate_request(req)
        assert result["tool_choice"] == "required"

    def test_tool_choice_none(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            tool_choice="none",
        )
        result = translate_request(req)
        assert result["tool_choice"] == "none"

    def test_tool_choice_specific_function(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            tool_choice={"type": "function", "function": {"name": "my_fn"}},
        )
        result = translate_request(req)
        assert result["tool_choice"] == {"type": "function", "name": "my_fn"}

    def test_tool_choice_not_set(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert "tool_choice" not in result


# --- Field mapping ---


class TestFieldMapping:
    def test_model_not_sent(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert not result["model"]

    def test_max_tokens_to_max_output_tokens(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            max_tokens=1024,
        )
        result = translate_request(req)
        assert result["max_output_tokens"] == 1024
        assert "max_tokens" not in result

    def test_max_tokens_none(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert "max_output_tokens" not in result

    def test_temperature_passed(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            temperature=0.5,
        )
        result = translate_request(req)
        assert result["temperature"] == 0.5

    def test_temperature_zero(self):
        req = ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="Hi")],
            temperature=0.0,
        )
        result = translate_request(req)
        assert result["temperature"] == 0.0

    def test_temperature_none(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert "temperature" not in result

    def test_stream_passed(self, streaming_chat_request):
        result = translate_request(streaming_chat_request)
        assert result["stream"] is True

    def test_store_always_false(self, simple_chat_request):
        result = translate_request(simple_chat_request)
        assert result["store"] is False

    def test_stream_options_ignored(self, streaming_chat_request):
        result = translate_request(streaming_chat_request)
        assert "stream_options" not in result
