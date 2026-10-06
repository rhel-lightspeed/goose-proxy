"""Tests for the /v1 router: responses passthrough, models, and health endpoints."""

from typing import AsyncIterator
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
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
    """Patch _build_client to return a mock httpx.AsyncClient."""
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    mock.aclose = AsyncMock(return_value=None)
    with patch("goose_proxy.v1._build_client", return_value=mock):
        yield mock


# --- Responses endpoint ---


class TestResponses:
    def test_non_streaming_success(self, test_client, mock_client):
        """Non-streaming response body is forwarded as raw bytes from the backend."""
        response_bytes = b'{"id":"resp_123","object":"response","created_at":1790707286}'
        mock_response = MagicMock()
        mock_response.content = response_bytes
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)

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
        mock_response = MagicMock()
        mock_response.content = response_bytes
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)

        resp = test_client.post("/v1/responses", json={"input": "Hello"})
        data = resp.json()

        assert data["created_at"] == 1790707286
        assert isinstance(data["created_at"], int)

    def test_non_streaming_clears_model(self, test_client, mock_client):
        """The client-supplied model is replaced with an empty string so the backend picks its own."""
        mock_response = MagicMock()
        mock_response.content = b'{"id":"resp_456","object":"response"}'
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)

        body = {
            "model": "RHEL-command-line-assistant",
            "input": "What is RHEL?",
            "store": False,
        }
        test_client.post("/v1/responses", json=body)

        posted_body = mock_client.post.call_args.kwargs["json"]
        assert posted_body["input"] == "What is RHEL?"
        assert posted_body["model"] == ""

    def test_non_streaming_without_model_still_sends_empty(self, test_client, mock_client):
        """Even when the client omits a model, the proxy injects an empty string."""
        mock_response = MagicMock()
        mock_response.content = b'{"id":"resp_789","object":"response"}'
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)

        resp = test_client.post(
            "/v1/responses",
            json={"input": "What is RHEL?"},
        )

        assert resp.status_code == 200
        posted_body = mock_client.post.call_args.kwargs["json"]
        assert posted_body["model"] == ""

    def test_non_streaming_returns_application_json(self, test_client, mock_client):
        """Non-streaming responses are returned with application/json content type."""
        mock_response = MagicMock()
        mock_response.content = b'{"id":"resp_101"}'
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)

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

        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = MagicMock(return_value=aiter_bytes_from(sse_bytes))

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

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
        """The 'stream' key is kept in the body sent to the backend."""
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = MagicMock(return_value=aiter_bytes_from([]))

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        test_client.post(
            "/v1/responses",
            json={"input": "Hello", "stream": True},
        )

        posted_body = mock_client.stream.call_args.kwargs["json"]
        assert posted_body["stream"] is True

    def test_streaming_cleanup_on_completion(self, test_client, mock_client):
        """The stream context manager is exited and client is closed after consumption."""
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = MagicMock(return_value=aiter_bytes_from([b"data: {}\n\n"]))

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        test_client.post("/v1/responses", json={"input": "Hello", "stream": True})

        mock_stream_cm.__aexit__.assert_called_once()
        mock_client.aclose.assert_called_once()

    def test_backend_http_error_propagates(self, test_client, mock_client):
        """4xx/5xx from the backend are returned as OpenAI-format error JSON."""
        exc = _make_http_status_error(403, {"error": {"message": "Forbidden"}})
        mock_client.post = AsyncMock(side_effect=exc)

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
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("All connection attempts failed"))

        resp = test_client.post(
            "/v1/responses",
            json={"model": "RHEL-command-line-assistant", "input": "Hello"},
        )
        data = resp.json()

        assert resp.status_code == 502
        assert data["error"]["type"] == "api_error"

    def test_streaming_connection_error_returns_502(self, test_client, mock_client):
        """A connection error during streaming returns a proper 502 JSON error."""
        mock_client.stream = MagicMock(side_effect=httpx.ConnectError("Connection refused"))

        resp = test_client.post(
            "/v1/responses",
            json={"model": "RHEL-command-line-assistant", "input": "Hello", "stream": True},
        )
        data = resp.json()

        assert resp.status_code == 502
        assert data["error"]["type"] == "api_error"

    def test_streaming_backend_http_error_returns_proper_status(self, test_client, mock_client):
        """A backend 5xx during streaming returns an OpenAI-format JSON error with the correct status."""
        request = httpx.Request("POST", "https://backend/responses")
        real_response = httpx.Response(503, json={"error": {"message": "Service Unavailable"}}, request=request)

        mock_response = MagicMock()
        mock_response.is_error = True
        mock_response.aread = AsyncMock(return_value=None)
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("503", request=request, response=real_response)
        )

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        resp = test_client.post(
            "/v1/responses",
            json={"model": "RHEL-command-line-assistant", "input": "Hello", "stream": True},
        )
        data = resp.json()

        assert resp.status_code == 503
        assert data["error"]["message"] == "Service Unavailable"
        assert data["error"]["type"] == "api_error"

    def test_streaming_mid_stream_error_emits_sse_error_event(self, test_client, mock_client):
        """A failure partway through streaming emits an SSE error event instead of silently truncating."""

        async def exploding_stream():
            yield b"event: response.created\n"
            yield b'data: {"type":"response.created"}\n\n'
            raise httpx.ReadError("Connection reset by peer")

        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = MagicMock(return_value=exploding_stream())

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        resp = test_client.post(
            "/v1/responses",
            json={"model": "RHEL-command-line-assistant", "input": "Hello", "stream": True},
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "response.created" in resp.text
        assert "event: error" in resp.text
        assert "Stream interrupted" in resp.text
        assert "Connection reset by peer" in resp.text

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


def _make_http_status_error(status_code, body):
    """Build an httpx.HTTPStatusError for test assertions."""
    request = httpx.Request("POST", "https://backend/v1/responses")
    response = httpx.Response(status_code, json=body, request=request)
    return httpx.HTTPStatusError(str(status_code), request=request, response=response)


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
