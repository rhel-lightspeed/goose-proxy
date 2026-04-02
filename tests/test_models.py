"""Tests for Pydantic model validation and helpers."""

from goose_proxy.models.responses import (
    Response,
    parse_stream_event,
)


class TestResponseDropUnknownOutputTypes:
    def test_keeps_known_types(self):
        resp = Response(
            id="r1",
            created_at=0,
            model="m",
            object="response",
            output=[
                {
                    "type": "message",
                    "id": "msg_1",
                    "content": [],
                    "role": "assistant",
                    "status": "completed",
                },
            ],
            status="completed",
        )
        assert len(resp.output) == 1

    def test_drops_unknown_types(self):
        resp = Response(
            id="r1",
            created_at=0,
            model="m",
            object="response",
            output=[
                {
                    "type": "mcp_list_tools",
                    "id": "mcp_1",
                },
                {
                    "type": "message",
                    "id": "msg_1",
                    "content": [],
                    "role": "assistant",
                    "status": "completed",
                },
            ],
            status="completed",
        )
        assert len(resp.output) == 1
        assert resp.output[0].type == "message"

    def test_all_unknown_types_results_in_empty(self):
        resp = Response(
            id="r1",
            created_at=0,
            model="m",
            object="response",
            output=[
                {"type": "mcp_list_tools", "id": "x"},
                {"type": "some_other", "id": "y"},
            ],
            status="completed",
        )
        assert resp.output == []

    def test_empty_output(self):
        resp = Response(
            id="r1",
            created_at=0,
            model="m",
            object="response",
            output=[],
            status="completed",
        )
        assert resp.output == []

    def test_keeps_function_call_type(self):
        resp = Response(
            id="r1",
            created_at=0,
            model="m",
            object="response",
            output=[
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "fn",
                    "arguments": "{}",
                    "status": "completed",
                },
            ],
            status="completed",
        )
        assert len(resp.output) == 1
        assert resp.output[0].type == "function_call"


class TestParseStreamEvent:
    def test_response_created(self):
        data = {
            "type": "response.created",
            "response": {
                "id": "r1",
                "created_at": 0,
                "model": "m",
                "object": "response",
                "output": [],
                "status": "in_progress",
            },
            "sequence_number": 0,
        }
        event = parse_stream_event(data)
        assert event is not None
        assert event.type == "response.created"

    def test_text_delta(self):
        data = {
            "type": "response.output_text.delta",
            "delta": "Hello",
            "content_index": 0,
            "item_id": "msg_1",
            "output_index": 0,
            "sequence_number": 1,
        }
        event = parse_stream_event(data)
        assert event is not None
        assert event.delta == "Hello"

    def test_function_call_arguments_delta(self):
        data = {
            "type": "response.function_call_arguments.delta",
            "delta": '{"key":',
            "item_id": "fc_1",
            "output_index": 0,
            "sequence_number": 2,
        }
        event = parse_stream_event(data)
        assert event is not None
        assert event.delta == '{"key":'

    def test_output_item_added_message(self):
        data = {
            "type": "response.output_item.added",
            "item": {
                "type": "message",
                "id": "msg_1",
                "content": [],
                "role": "assistant",
                "status": "in_progress",
            },
            "output_index": 0,
            "sequence_number": 1,
        }
        event = parse_stream_event(data)
        assert event is not None
        assert event.type == "response.output_item.added"

    def test_output_item_added_function_call(self):
        data = {
            "type": "response.output_item.added",
            "item": {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "fn",
                "arguments": "",
                "status": "in_progress",
            },
            "output_index": 0,
            "sequence_number": 1,
        }
        event = parse_stream_event(data)
        assert event is not None

    def test_output_item_added_unknown_type_returns_none(self):
        data = {
            "type": "response.output_item.added",
            "item": {"type": "mcp_list_tools", "id": "x"},
            "output_index": 0,
            "sequence_number": 1,
        }
        event = parse_stream_event(data)
        assert event is None

    def test_unknown_event_type_returns_none(self):
        data = {"type": "response.something_unknown", "foo": "bar"}
        event = parse_stream_event(data)
        assert event is None

    def test_missing_type_returns_none(self):
        data = {"foo": "bar"}
        event = parse_stream_event(data)
        assert event is None

    def test_response_completed(self):
        data = {
            "type": "response.completed",
            "response": {
                "id": "r1",
                "created_at": 0,
                "model": "m",
                "object": "response",
                "output": [],
                "status": "completed",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            },
            "sequence_number": 10,
        }
        event = parse_stream_event(data)
        assert event is not None
        assert event.type == "response.completed"
        assert event.response.usage.total_tokens == 15
