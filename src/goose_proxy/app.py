import logging

from fastapi import FastAPI

from goose_proxy import v1
from goose_proxy.exceptions import register_exception_handlers
from goose_proxy.middleware import TimeoutMiddleware


logger = logging.getLogger(__name__)


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
)

app.add_middleware(TimeoutMiddleware)

register_exception_handlers(app)


@app.get("/health")
async def health_check() -> None:
    """Health check endpoint for infrastructure probes."""
    return None


app.include_router(v1.router)
