"""Translate Responses API responses to Chat Completions format."""

from goose_proxy.models.chat import (
    ChatCompletion,
    ChatCompletionMessageToolCall,
    ChatCompletionResponseMessage,
    Choice,
    CompletionUsage,
    Function,
)
from goose_proxy.models.responses import (
    OutputItem,
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)


def _extract_text(output_message: ResponseOutputMessage) -> str | None:
    """Extract concatenated text from a ResponseOutputMessage's content parts."""
    parts = []
    for content_part in output_message.content:
        if isinstance(content_part, ResponseOutputText):
            parts.append(content_part.text)
    return "".join(parts) if parts else None


def _extract_tool_calls(
    output: list[OutputItem],
) -> list[ChatCompletionMessageToolCall] | None:
    """Extract tool calls from the response output items."""
    tool_calls = []
    for item in output:
        if isinstance(item, ResponseFunctionToolCall):
            tool_calls.append(
                ChatCompletionMessageToolCall(
                    id=item.call_id,
                    type="function",
                    function=Function(
                        name=item.name,
                        arguments=item.arguments,
                    ),
                )
            )
    return tool_calls if tool_calls else None


def _determine_finish_reason(
    response: Response,
    has_tool_calls: bool,
) -> str:
    """Determine the Chat Completions finish_reason from the response."""
    if has_tool_calls:
        return "tool_calls"

    if response.status == "incomplete":
        return "length"

    return "stop"


def _translate_usage(response: Response) -> CompletionUsage | None:
    """Translate Responses API usage to Chat Completions usage."""
    if response.usage is None:
        return None

    return CompletionUsage(
        prompt_tokens=response.usage.input_tokens,
        completion_tokens=response.usage.output_tokens,
        total_tokens=response.usage.total_tokens,
    )


def translate_response(response: Response, model: str | None) -> ChatCompletion:
    """Translate a Responses API Response into a ChatCompletion.

    Args:
        response: The Responses API response object.
        model: The original model name from the request, or None to use the response model.
    """
    content: str | None = None
    for item in response.output:
        if isinstance(item, ResponseOutputMessage):
            content = _extract_text(item)
            break

    tool_calls = _extract_tool_calls(response.output)
    has_tool_calls = tool_calls is not None
    finish_reason = _determine_finish_reason(response, has_tool_calls)

    message = ChatCompletionResponseMessage(
        role="assistant",
        content=content,
        tool_calls=tool_calls,
    )

    choice = Choice(
        index=0,
        message=message,
        finish_reason=finish_reason,
    )

    return ChatCompletion(
        id=response.id,
        object="chat.completion",
        created=int(response.created_at),
        model=model or response.model,
        choices=[choice],
        usage=_translate_usage(response),
    )
