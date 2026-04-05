import logging

from contextlib import asynccontextmanager

import httpx

from fastapi import FastAPI

from goose_proxy.config import get_settings
from goose_proxy.exceptions import register_exception_handlers
from goose_proxy.middleware import TimeoutMiddleware
from goose_proxy.routers import health
from goose_proxy.routers import v1


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    backend = settings.backend
    cert = (str(backend.auth.cert_file), str(backend.auth.key_file))

    http_client = httpx.AsyncClient(
        base_url=backend.endpoint,
        cert=cert,
        timeout=backend.timeout,
        proxy=backend.proxy or None,
        headers={"Accept": "application/json"},
    )
    app.state.http_client = http_client
    yield
    await http_client.aclose()


app = FastAPI(
    title="goose-proxy",
    description="A proxy that translates OpenAI Chat Completions API to Responses API",
    version="0.1.0",
    contact={"name": "RHEL Lightspeed Team", "email": "rhel-lightspeed-sst@redhat.com"},
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    root_path="/",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(TimeoutMiddleware)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(v1.router, prefix="/v1")
