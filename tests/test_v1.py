import json

from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import openai
import pytest

from fastapi.testclient import TestClient
from openai.types.responses import Response
from openai.types.responses import ResponseCompletedEvent
from openai.types.responses import ResponseCreatedEvent
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses import ResponseOutputMessage
from openai.types.responses import ResponseOutputText
from openai.types.responses import ResponseTextDeltaEvent
from openai.types.responses import ResponseUsage

from goose_proxy.app import app
from goose_proxy.config import Auth
from goose_proxy.config import Backend
from goose_proxy.config import Settings
from goose_proxy.v1 import get_openai_client


def _make_usage():
    return ResponseUsage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        input_tokens_details={"cached_tokens": 0},
        output_tokens_details={"reasoning_tokens": 0},
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
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
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
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status="completed",
        usage=_make_usage(),
    )


@pytest.fixture
def mock_openai_client():
    """Create a mock AsyncOpenAI client."""
    client = MagicMock()
    client.responses = MagicMock()
    client.responses.create = AsyncMock()
    return client


@pytest.fixture
def test_client(mock_openai_client):
    """FastAPI test client with mocked OpenAI dependency."""
    app.dependency_overrides[get_openai_client] = lambda: mock_openai_client

    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def text_response_fixture():
    return _make_text_response()


@pytest.fixture
def tool_call_response_fixture():
    return _make_tool_call_response()


# --- Chat completions endpoint ---


class TestChatCompletions:
    def test_chat_completions_success(self, test_client, mock_openai_client, text_response_fixture):
        mock_openai_client.responses.create.return_value = text_response_fixture
        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "rhel-lightspeed/vertex",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Hello!"
        assert data["choices"][0]["finish_reason"] == "stop"

    def test_chat_completions_with_tools(self, test_client, mock_openai_client, tool_call_response_fixture):
        mock_openai_client.responses.create.return_value = tool_call_response_fixture
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
        assert resp.status_code == 200
        data = resp.json()
        tc = data["choices"][0]["message"]["tool_calls"]

        assert data["choices"][0]["finish_reason"] == "tool_calls"
        assert len(tc) == 1
        assert tc[0]["function"]["name"] == "get_weather"

    def test_chat_completions_streaming(self, test_client, mock_openai_client):
        base_resp = Response(
            id="resp_stream",
            created_at=1700000000,
            model="rhel-lightspeed/vertex",
            object="response",
            output=[],
            parallel_tool_calls=True,
            tool_choice="auto",
            tools=[],
            status="in_progress",
            usage=None,
        )

        completed_resp = Response(
            id="resp_stream",
            created_at=1700000000,
            model="rhel-lightspeed/vertex",
            object="response",
            output=[],
            parallel_tool_calls=True,
            tool_choice="auto",
            tools=[],
            status="completed",
            usage=_make_usage(),
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
                logprobs=[],
            ),
            ResponseCompletedEvent(
                response=completed_resp,
                sequence_number=2,
                type="response.completed",
            ),
        ]

        async def mock_stream_iter():
            for e in events:
                yield e

        mock_openai_client.responses.create.return_value = mock_stream_iter()

        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "rhel-lightspeed/vertex",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        lines = [line for line in resp.text.split("\n\n") if line.strip()]
        assert len(lines) >= 3  # role + text + completed + [DONE]
        assert lines[-1].strip() == "data: [DONE]"

        # Check first data chunk has role
        first = json.loads(lines[0].removeprefix("data: "))
        assert first["choices"][0]["delta"]["role"] == "assistant"

    def test_chat_completions_backend_error(self, test_client, mock_openai_client):
        error_response = httpx.Response(
            status_code=404,
            json={"error": {"message": "Model not found"}},
            request=httpx.Request("POST", "http://test"),
        )
        mock_openai_client.responses.create.side_effect = openai.NotFoundError(
            message="Not Found",
            response=error_response,
            body={"error": {"message": "Model not found"}},
        )
        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "nonexistent/model",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
        assert resp.status_code == 404
        data = resp.json()

        assert data["error"]["message"] == "Model not found"

    def test_chat_completions_invalid_request(self, test_client):
        resp = test_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )

        assert resp.status_code == 422

    def test_chat_completions_missing_certificates(self, test_client):
        fake_settings = Settings(
            backend=Backend(
                auth=Auth(
                    cert_file=Path("/nonexistent/cert.pem"),
                    key_file=Path("/nonexistent/key.pem"),
                ),
            ),
        )

        with patch("goose_proxy.v1.get_settings", return_value=fake_settings):
            get_openai_client.cache_clear()
            app.dependency_overrides.pop(get_openai_client, None)

            resp = test_client.post(
                "/v1/chat/completions",
                json={
                    "model": "rhel-lightspeed/vertex",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

        data = resp.json()

        assert resp.status_code == 502
        assert "System is not registered" in data["error"]["message"]
        assert "subscription-manager register" in data["error"]["message"]


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
