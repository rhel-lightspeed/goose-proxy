"""Pydantic models for the Responses API."""

from __future__ import annotations

import logging
from typing import Annotated, Literal, Union, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# --- Response output types ---


class ResponseOutputText(BaseModel):
    type: Literal["output_text"] = "output_text"
    text: str
    annotations: list = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class ResponseOutputMessage(BaseModel):
    type: Literal["message"] = "message"
    id: str
    content: list[ResponseOutputText]
    role: str
    status: str

    model_config = ConfigDict(extra="ignore")


class ResponseFunctionToolCall(BaseModel):
    type: Literal["function_call"] = "function_call"
    id: str
    call_id: str
    name: str
    arguments: str
    status: str

    model_config = ConfigDict(extra="ignore")


OutputItem = Annotated[
    Union[ResponseOutputMessage, ResponseFunctionToolCall],
    Field(discriminator="type"),
]

_KNOWN_OUTPUT_TYPES = {"message", "function_call"}


class ResponseUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int

    model_config = ConfigDict(extra="ignore")


class Response(BaseModel):
    id: str
    created_at: int
    model: str
    object: str
    output: list[OutputItem]
    status: str
    usage: ResponseUsage | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("output", mode="before")
    @classmethod
    def drop_unknown_output_types(cls, items: list) -> list:
        """Filter out output items with types the proxy doesn't translate.

        The Responses API can return output types (e.g. mcp_list_tools) that
        this proxy doesn't need to handle. Dropping them here avoids
        validation errors from the discriminated union.
        """
        known = []
        for item in items:
            item_type = (
                item.get("type", "")
                if isinstance(item, dict)
                else getattr(item, "type", "")
            )
            if item_type in _KNOWN_OUTPUT_TYPES:
                known.append(item)
            else:
                logger.debug("Skipping unknown output type: %s", item_type)
        return known


# --- Streaming event types ---


class ResponseCreatedEvent(BaseModel):
    type: Literal["response.created"] = "response.created"
    response: Response
    sequence_number: int


class ResponseTextDeltaEvent(BaseModel):
    type: Literal["response.output_text.delta"] = "response.output_text.delta"
    delta: str
    content_index: int
    item_id: str
    output_index: int
    sequence_number: int

    model_config = ConfigDict(extra="ignore")


class ResponseOutputItemAddedEvent(BaseModel):
    type: Literal["response.output_item.added"] = "response.output_item.added"
    item: OutputItem
    output_index: int
    sequence_number: int


class ResponseFunctionCallArgumentsDeltaEvent(BaseModel):
    type: Literal["response.function_call_arguments.delta"] = (
        "response.function_call_arguments.delta"
    )
    delta: str
    item_id: str
    output_index: int
    sequence_number: int


class ResponseCompletedEvent(BaseModel):
    type: Literal["response.completed"] = "response.completed"
    response: Response
    sequence_number: int


StreamEvent = Union[
    ResponseCreatedEvent,
    ResponseTextDeltaEvent,
    ResponseOutputItemAddedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseCompletedEvent,
]

_EVENT_TYPES: dict[str, type[BaseModel]] = {
    "response.created": ResponseCreatedEvent,
    "response.output_text.delta": ResponseTextDeltaEvent,
    "response.output_item.added": ResponseOutputItemAddedEvent,
    "response.function_call_arguments.delta": ResponseFunctionCallArgumentsDeltaEvent,
    "response.completed": ResponseCompletedEvent,
}


def parse_stream_event(data: dict) -> StreamEvent | None:
    """Parse a raw event dict into a typed streaming event model.

    Returns None for unknown event types or events containing
    output items with types the proxy doesn't translate.
    """
    event_cls = _EVENT_TYPES.get(data.get("type", ""))
    if event_cls is None:
        return None

    # Skip output_item.added events for item types we don't handle
    if event_cls is ResponseOutputItemAddedEvent:
        item_type = data.get("item", {}).get("type", "")
        if item_type not in _KNOWN_OUTPUT_TYPES:
            logger.debug("Skipping output_item.added for unknown type: %s", item_type)
            return None

    return cast(StreamEvent, event_cls.model_validate(data))
