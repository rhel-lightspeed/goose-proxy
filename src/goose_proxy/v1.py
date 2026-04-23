import json
import logging
import ssl
import typing as t
import urllib.error
import urllib.request

from collections.abc import Iterator

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi.responses import StreamingResponse

from goose_proxy.config import get_settings
from goose_proxy.exceptions import CertificateInitializationError
from goose_proxy.models.chat import ChatCompletionRequest
from goose_proxy.models.chat import ModelInfo
from goose_proxy.models.chat import ModelsResponse
from goose_proxy.models.responses import parse_stream_event
from goose_proxy.models.responses import Response
from goose_proxy.models.responses import StreamEvent
from goose_proxy.translators import translate_request
from goose_proxy.translators import translate_response
from goose_proxy.translators import translate_stream


logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/v1")


class BackendClient:
    def __init__(
        self,
        base_url: str,
        ssl_context: ssl.SSLContext,
        timeout: int,
        headers: dict,
        proxy: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.ssl_context = ssl_context
        self.timeout = timeout
        self.headers = headers

        if proxy:
            proxy_handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
            https_handler = urllib.request.HTTPSHandler(context=self.ssl_context)
            self.opener = urllib.request.build_opener(proxy_handler, https_handler)
        else:
            https_handler = urllib.request.HTTPSHandler(context=self.ssl_context)
            self.opener = urllib.request.build_opener(https_handler)

    def post(self, path: str, body: dict) -> urllib.request.Request:
        url = self.base_url + path
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        for key, value in self.headers.items():
            req.add_header(key, value)

        req.add_header("Content-Type", "application/json")

        return req

    def send(self, req: urllib.request.Request):
        try:
            return self.opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError:
            logger.debug(
                "Request that caused backend error\n\t\tRequest: %s %s\n\t\tRequest headers: %s",
                req.get_method(),
                req.full_url,
                dict(req.headers),
            )
            raise

    @classmethod
    def create(cls) -> "BackendClient":
        logger.debug("Getting backend client")
        settings = get_settings()
        backend = settings.backend

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        try:
            ctx.load_cert_chain(str(backend.auth.cert_file), str(backend.auth.key_file))
        except (FileNotFoundError, ssl.SSLError) as err:
            raise CertificateInitializationError() from err
        ctx.load_default_certs()

        client = cls(
            base_url=backend.endpoint,
            ssl_context=ctx,
            timeout=backend.timeout,
            proxy=backend.proxy,
            headers={
                "Accept": "application/json",
                "X-LCS-Merge-Server-Tools": "true",
            },
        )

        return client

    def create_response(self, **params) -> Response:
        req = self.post("/responses", body=params)
        with self.send(req) as resp:
            data = json.loads(resp.read().decode())

        return Response.model_validate(data)

    def open_stream(self, **params):
        """Open a streaming connection to the backend.

        Returns the raw response object. Raises urllib.error.HTTPError on
        error status codes before any data is consumed, allowing callers
        to handle the error before committing to a StreamingResponse.
        """
        req = self.post("/responses", body=params)

        return self.send(req)

    @staticmethod
    def iter_stream_events(resp: t.IO[bytes]) -> Iterator[StreamEvent]:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line or line.startswith("event:"):
                continue

            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    break

                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed SSE data: %s", payload[:120])
                    continue

                event = parse_stream_event(data)
                if event is not None:
                    yield event

    def stream_response(self, **params) -> Iterator[StreamEvent]:
        with self.open_stream(**params) as resp:
            yield from self.iter_stream_events(resp)


@router.post("/chat/completions", response_model_exclude_none=True)
async def chat_completions(
    data: ChatCompletionRequest,
    client: t.Annotated[BackendClient, Depends(BackendClient.create)],
):
    params = translate_request(data)
    if data.stream:
        resp = client.open_stream(**params)

        def generate():
            try:
                for line in translate_stream(client.iter_stream_events(resp), data.model):
                    yield line
            finally:
                resp.close()

        return StreamingResponse(generate(), media_type="text/event-stream")

    response = client.create_response(**params)

    return translate_response(response, data.model)


@router.get("/models")
async def list_models(_: Request) -> ModelsResponse:
    """Return fixed model info instead of querying the backend.

    Always returns 'RHEL-command-line-assistant' as the available model.
    This simplifies the proxy by avoiding dynamic model lookups.
    """
    return ModelsResponse(
        data=[
            ModelInfo(
                id="RHEL-command-line-assistant",
                owned_by="command-line-assistant",
            )
        ]
    )
