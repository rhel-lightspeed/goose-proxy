import io
import json
import urllib.error

from unittest.mock import MagicMock

import pytest

from fastapi.testclient import TestClient

from goose_proxy.app import app
from goose_proxy.models.responses import Response
from goose_proxy.models.responses import ResponseCompletedEvent
from goose_proxy.models.responses import ResponseCreatedEvent
from goose_proxy.models.responses import ResponseFunctionToolCall
from goose_proxy.models.responses import ResponseOutputMessage
from goose_proxy.models.responses import ResponseOutputText
from goose_proxy.models.responses import ResponseTextDeltaEvent
from goose_proxy.models.responses import ResponseUsage
from goose_proxy.v1 import BackendClient


def _make_usage():
    return ResponseUsage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
    )


def _make_text_response():
    return Response(
        id="resp_test",
        created_at=1700000000,
        model="rhel-lightspeed/vertex",
        object="response",
        output=[
            ResponseOutputMessage(
                id="msg_1",
                content=[ResponseOutputText(annotations=[], text="Hello!", type="output_text")],
                role="assistant",
                status="completed",
                type="message",
            )
        ],
        status="completed",
        usage=_make_usage(),
    )


def _make_tool_call_response():
    return Response(
        id="resp_tools",
        created_at=1700000000,
        model="rhel-lightspeed/vertex",
        object="response",
        output=[
            ResponseFunctionToolCall(
                arguments='{"location": "London"}',
                call_id="call_abc",
                name="get_weather",
                type="function_call",
                id="fc_1",
                status="completed",
            )
        ],
        status="completed",
        usage=_make_usage(),
    )


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def mock_backend():
    mock = MagicMock()

    def _mock_backend():
        return mock

    app.dependency_overrides[BackendClient.create] = _mock_backend
    yield mock

    app.dependency_overrides.clear()


@pytest.fixture
def text_response_fixture():
    return _make_text_response()


@pytest.fixture
def tool_call_response_fixture():
    return _make_tool_call_response()


# --- Chat completions endpoint ---


class TestChatCompletions:
    def test_chat_completions_success(self, test_client, mock_backend, text_response_fixture):
        mock_backend.create_response.return_value = text_response_fixture

        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "rhel-lightspeed/vertex",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        data = resp.json()

        assert resp.status_code == 200
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Hello!"
        assert data["choices"][0]["finish_reason"] == "stop"

    def test_chat_completions_with_tools(self, test_client, mock_backend, tool_call_response_fixture):
        mock_backend.create_response.return_value = tool_call_response_fixture

        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "rhel-lightspeed/vertex",
                "messages": [{"role": "user", "content": "Weather?"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get weather",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            },
        )
        data = resp.json()
        tc = data["choices"][0]["message"]["tool_calls"]

        assert resp.status_code == 200
        assert data["choices"][0]["finish_reason"] == "tool_calls"
        assert len(tc) == 1
        assert tc[0]["function"]["name"] == "get_weather"

    def test_chat_completions_streaming(self, test_client, mock_backend):
        base_resp = Response(
            id="resp_stream",
            created_at=1700000000,
            model="rhel-lightspeed/vertex",
            object="response",
            output=[],
            status="in_progress",
            usage=None,
        )

        usage = ResponseUsage(
            input_tokens=10,
            output_tokens=2,
            total_tokens=12,
        )

        completed_resp = Response(
            id="resp_stream",
            created_at=1700000000,
            model="rhel-lightspeed/vertex",
            object="response",
            output=[],
            status="completed",
            usage=usage,
        )

        events = [
            ResponseCreatedEvent(response=base_resp, sequence_number=0, type="response.created"),
            ResponseTextDeltaEvent(
                content_index=0,
                delta="Hi",
                item_id="msg_1",
                output_index=0,
                sequence_number=1,
                type="response.output_text.delta",
            ),
            ResponseCompletedEvent(
                response=completed_resp,
                sequence_number=2,
                type="response.completed",
            ),
        ]

        mock_backend.stream_response.return_value = iter(events)

        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "rhel-lightspeed/vertex",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )
        lines = [line for line in resp.text.split("\n\n") if line.strip()]

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert len(lines) >= 3  # role + text + completed + [DONE]
        assert lines[-1].strip() == "data: [DONE]"

        # Check first data chunk has role
        first = json.loads(lines[0].removeprefix("data: "))
        assert first["choices"][0]["delta"]["role"] == "assistant"

    def test_chat_completions_backend_error(self, test_client, mock_backend):
        error_body = b'{"error": {"message": "Model not found"}}'
        exc = urllib.error.HTTPError(
            url="http://test/responses",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(error_body),
        )
        mock_backend.create_response.side_effect = exc

        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "nonexistent/model",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
        data = resp.json()

        assert resp.status_code == 404
        assert data["error"]["message"] == "Model not found"

    def test_chat_completions_invalid_request(self, test_client, mock_backend):
        resp = test_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )

        assert resp.status_code == 422


# --- Models endpoint ---


class TestModels:
    def test_list_models_success(self, test_client):
        resp = test_client.get("/v1/models")
        data = resp.json()

        assert resp.status_code == 200
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == "RHEL-command-line-assistant"

    def test_list_models_owned_by(self, test_client):
        resp = test_client.get("/v1/models")
        data = resp.json()

        assert data["data"][0]["owned_by"] == "command-line-assistant"


# --- Health endpoint ---


class TestHealth:
    def test_health_check(self, test_client):
        resp = test_client.get("/health")

        assert resp.status_code == 200
