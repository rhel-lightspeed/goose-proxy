"""Tests for the /v1 router: responses passthrough, models, and health endpoints."""

from typing import AsyncIterator
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import openai
import pytest

from fastapi.testclient import TestClient

from goose_proxy.app import app
from goose_proxy.exceptions import CertificateInitializationError


async def aiter_bytes_from(chunks: list) -> AsyncIterator:
    """Wrap a list as an async byte iterator for use in stream mocks."""
    for chunk in chunks:
        yield chunk


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def mock_client():
    """Patch _build_client to return a mock AsyncOpenAI."""
    mock = MagicMock(spec=openai.AsyncOpenAI)
    with patch("goose_proxy.v1._build_client", return_value=mock):
        yield mock


# --- Responses endpoint ---


class TestResponses:
    def test_non_streaming_success(self, test_client, mock_client):
        """Non-streaming response body is forwarded as raw bytes from the backend."""
        response_bytes = b'{"id":"resp_123","object":"response","created_at":1790707286}'
        mock_raw = MagicMock()
        mock_raw.content = response_bytes
        mock_client.responses.with_raw_response.create = AsyncMock(return_value=mock_raw)

        resp = test_client.post(
            "/v1/responses",
            json={
                "model": "RHEL-command-line-assistant",
                "input": [{"role": "user", "content": "Hello"}],
            },
        )
        data = resp.json()

        assert resp.status_code == 200
        assert data["id"] == "resp_123"
        assert data["created_at"] == 1790707286

    def test_non_streaming_preserves_integer_types(self, test_client, mock_client):
        """Integer fields like created_at are not converted to floats."""
        response_bytes = b'{"id":"resp_456","created_at":1790707286,"usage":{"input_tokens":10,"output_tokens":5}}'
        mock_raw = MagicMock()
        mock_raw.content = response_bytes
        mock_client.responses.with_raw_response.create = AsyncMock(return_value=mock_raw)

        resp = test_client.post("/v1/responses", json={"input": "Hello"})
        data = resp.json()

        assert data["created_at"] == 1790707286
        assert isinstance(data["created_at"], int)

    def test_non_streaming_clears_model(self, test_client, mock_client):
        """The client-supplied model is replaced with an empty string so the backend picks its own."""
        mock_raw = MagicMock()
        mock_raw.content = b'{"id":"resp_456","object":"response"}'
        mock_client.responses.with_raw_response.create = AsyncMock(return_value=mock_raw)

        body = {
            "model": "RHEL-command-line-assistant",
            "input": "What is RHEL?",
            "store": False,
        }
        test_client.post("/v1/responses", json=body)

        call_kwargs = mock_client.responses.with_raw_response.create.call_args.kwargs
        assert call_kwargs["input"] == "What is RHEL?"
        assert call_kwargs["model"] == ""

    def test_non_streaming_without_model_still_sends_empty(self, test_client, mock_client):
        """Even when the client omits a model, the proxy injects an empty string."""
        mock_raw = MagicMock()
        mock_raw.content = b'{"id":"resp_789","object":"response"}'
        mock_client.responses.with_raw_response.create = AsyncMock(return_value=mock_raw)

        resp = test_client.post(
            "/v1/responses",
            json={"input": "What is RHEL?"},
        )

        assert resp.status_code == 200
        call_kwargs = mock_client.responses.with_raw_response.create.call_args.kwargs
        assert call_kwargs["model"] == ""

    def test_non_streaming_returns_application_json(self, test_client, mock_client):
        """Non-streaming responses are returned with application/json content type."""
        mock_raw = MagicMock()
        mock_raw.content = b'{"id":"resp_101"}'
        mock_client.responses.with_raw_response.create = AsyncMock(return_value=mock_raw)

        resp = test_client.post("/v1/responses", json={"input": "Hello"})

        assert "application/json" in resp.headers["content-type"]

    def test_streaming_success(self, test_client, mock_client):
        """Streaming response forwards raw SSE bytes from the backend."""
        sse_bytes = [
            b"event: response.created\n",
            b'data: {"type":"response.created","response":{"created_at":1790707286}}\n\n',
            b"event: response.output_text.delta\n",
            b'data: {"type":"response.output_text.delta","delta":"Hi"}\n\n',
            b"data: [DONE]\n\n",
        ]

        mock_content = MagicMock()
        mock_content.iter_bytes = MagicMock(return_value=aiter_bytes_from(sse_bytes))

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_content)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.responses.with_streaming_response.create = MagicMock(return_value=mock_ctx)

        resp = test_client.post(
            "/v1/responses",
            json={
                "model": "RHEL-command-line-assistant",
                "input": "Hello",
                "stream": True,
            },
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "response.created" in resp.text
        assert "response.output_text.delta" in resp.text
        assert "[DONE]" in resp.text
        assert "1790707286" in resp.text

    def test_streaming_keeps_stream_in_body(self, test_client, mock_client):
        """The 'stream' key is kept in the body for with_streaming_response.create()."""
        mock_content = MagicMock()
        mock_content.iter_bytes = MagicMock(return_value=aiter_bytes_from([]))

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_content)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.responses.with_streaming_response.create = MagicMock(return_value=mock_ctx)

        test_client.post(
            "/v1/responses",
            json={"input": "Hello", "stream": True},
        )

        call_kwargs = mock_client.responses.with_streaming_response.create.call_args.kwargs
        assert call_kwargs["stream"] is True

    def test_streaming_calls_aexit_on_completion(self, test_client, mock_client):
        """The stream context is properly cleaned up via __aexit__."""
        mock_content = MagicMock()
        mock_content.iter_bytes = MagicMock(return_value=aiter_bytes_from([b"data: {}\n\n"]))

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_content)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.responses.with_streaming_response.create = MagicMock(return_value=mock_ctx)

        test_client.post("/v1/responses", json={"input": "Hello", "stream": True})

        mock_ctx.__aexit__.assert_called_once_with(None, None, None)

    def test_backend_http_error_propagates(self, test_client, mock_client):
        """4xx/5xx from the backend are returned as OpenAI-format error JSON."""
        error_body = {"error": {"message": "Forbidden"}}
        exc = _make_api_status_error(403, error_body)
        mock_client.responses.with_raw_response.create = AsyncMock(side_effect=exc)

        resp = test_client.post(
            "/v1/responses",
            json={"model": "RHEL-command-line-assistant", "input": "Hello"},
        )
        data = resp.json()

        assert resp.status_code == 403
        assert data["error"]["message"] == "Forbidden"
        assert data["error"]["type"] == "api_error"

    def test_backend_connection_error_propagates(self, test_client, mock_client):
        """Connection failures return a 502 error."""
        mock_client.responses.with_raw_response.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock(), message="All connection attempts failed")
        )

        resp = test_client.post(
            "/v1/responses",
            json={"model": "RHEL-command-line-assistant", "input": "Hello"},
        )
        data = resp.json()

        assert resp.status_code == 502
        assert data["error"]["type"] == "api_error"

    def test_streaming_connection_error_before_headers(self, test_client, mock_client):
        """A connection error during stream open is caught before headers are sent."""
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock(), message="Connection refused")
        )
        mock_client.responses.with_streaming_response.create = MagicMock(return_value=mock_ctx)

        resp = test_client.post(
            "/v1/responses",
            json={"model": "RHEL-command-line-assistant", "input": "Hello", "stream": True},
        )
        data = resp.json()

        assert resp.status_code == 502
        assert data["error"]["type"] == "api_error"

    def test_missing_certificates_returns_502(self, test_client):
        """Missing RHSM certificates produce a clear 502 with registration instructions."""
        with patch("goose_proxy.v1._build_client", side_effect=CertificateInitializationError()):
            resp = test_client.post(
                "/v1/responses",
                json={"model": "RHEL-command-line-assistant", "input": "Hello"},
            )

        data = resp.json()

        assert resp.status_code == 502
        assert "System is not registered" in data["error"]["message"]
        assert "subscription-manager register" in data["error"]["message"]


def _make_api_status_error(status_code, body):
    """Build an openai.APIStatusError for test assertions."""
    request = httpx.Request("POST", "https://backend/v1/responses")
    response = httpx.Response(status_code, json=body, request=request)
    return openai.APIStatusError(str(status_code), response=response, body=body)


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
