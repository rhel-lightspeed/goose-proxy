"""Translate Chat Completions requests to Responses API parameters."""

from typing import Any

from goose_proxy.models.chat import (
    ChatCompletionRequest,
    ChatMessage,
    ContentPart,
    ImageUrlContentPart,
    TextContentPart,
)


def _translate_tool_choice(
    tool_choice: str | dict[str, Any],
) -> str | dict[str, Any]:
    """Translate tool_choice from Chat Completions to Responses API format.

    String values ("auto", "required", "none") pass through.
    Object form {"type": "function", "function": {"name": "fn"}} is unwrapped to
    {"type": "function", "name": "fn"}.
    """
    if isinstance(tool_choice, str):
        return tool_choice

    if (
        isinstance(tool_choice, dict)
        and tool_choice.get("type") == "function"
        and "function" in tool_choice
    ):
        return {
            "type": "function",
            "name": tool_choice["function"]["name"],
        }

    return tool_choice


def _translate_tools(
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten tool definitions from Chat Completions to Responses API format.

    Chat Completions: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    Responses API:    {"type": "function", "name": ..., "description": ..., "parameters": ...}
    """
    translated = []
    for tool in tools:
        fn = tool.get("function", {})
        entry: dict[str, Any] = {
            "type": "function",
            "name": fn["name"],
        }
        if fn.get("description") is not None:
            entry["description"] = fn["description"]
        if fn.get("parameters") is not None:
            entry["parameters"] = fn["parameters"]
        translated.append(entry)
    return translated


def _translate_user_content(
    content: str | list[ContentPart] | None,
) -> list[dict[str, Any]]:
    """Convert user message content to Responses API content parts.

    Handles both plain string content and array content (text + image_url blocks).
    """
    if content is None or isinstance(content, str):
        return [{"type": "input_text", "text": content or ""}]

    parts: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, TextContentPart):
            parts.append({"type": "input_text", "text": block.text})
        elif isinstance(block, ImageUrlContentPart):
            parts.append({"type": "input_image", "image_url": block.image_url.url})
    return parts or [{"type": "input_text", "text": ""}]


def _translate_messages(
    messages: list[ChatMessage],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert Chat Completions messages to Responses API input items.

    Returns (instructions, input_items) where instructions is the concatenated
    system messages and input_items is the list of Responses API input items.
    """
    system_parts: list[str] = []
    input_items: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == "system":
            if msg.content:
                if isinstance(msg.content, str):
                    system_parts.append(msg.content)
                else:
                    for block in msg.content:
                        if isinstance(block, TextContentPart):
                            system_parts.append(block.text)

        elif msg.role == "user":
            content_parts = _translate_user_content(msg.content)
            input_items.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": content_parts,
                }
            )

        elif msg.role == "assistant":
            if msg.content:
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": msg.content}],
                    }
                )

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": tc.id,
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    )

        elif msg.role == "tool":
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id or "",
                    "output": msg.content or "",
                }
            )

    instructions = "\n\n".join(system_parts) if system_parts else None
    return instructions, input_items


def translate_request(request: ChatCompletionRequest) -> dict[str, Any]:
    """Translate a Chat Completions request into kwargs for client.responses.create().

    This is the main entry point for request translation.
    """
    instructions, input_items = _translate_messages(request.messages)

    params: dict[str, Any] = {
        "model": "",
        "input": input_items,
        "stream": request.stream,
        "store": False,
    }

    if instructions:
        params["instructions"] = instructions

    if request.tools:
        tools_data = [tool.model_dump() for tool in request.tools]
        params["tools"] = _translate_tools(tools_data)

    if request.tool_choice:
        params["tool_choice"] = _translate_tool_choice(request.tool_choice)

    if request.temperature is not None:
        params["temperature"] = request.temperature

    if request.max_tokens:
        params["max_output_tokens"] = request.max_tokens

    return params
