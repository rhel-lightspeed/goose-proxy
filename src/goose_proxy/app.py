import logging
import time

import httpx
import waitress

from flask import Flask
from flask import request as flask_request

from goose_proxy.config import get_settings
from goose_proxy.exceptions import register_error_handlers
from goose_proxy.middleware import TimeoutMiddleware
from goose_proxy.routers import v1


logger = logging.getLogger(__name__)

ACCESS_LOG_FORMAT = '%s - - [%s] "%s %s %s" %d %s'


def create_app() -> Flask:
    app = Flask(__name__)

    register_error_handlers(app)

    @app.before_request
    def ensure_http_client():
        if "http_client" not in app.config:
            _init_http_client(app)

    @app.before_request
    def mark_start_time():
        flask_request._start_time = time.time()  # ty: ignore[unresolved-attribute]

    @app.after_request
    def log_request(response):
        access_logger = logging.getLogger("goose_proxy.access")
        elapsed = ""
        start = getattr(flask_request, "_start_time", None)
        if start is not None:
            elapsed = f" ({(time.time() - start) * 1000:.0f}ms)"

        access_logger.info(
            ACCESS_LOG_FORMAT + "%s",
            flask_request.remote_addr,
            time.strftime("%d/%b/%Y %H:%M:%S"),
            flask_request.method,
            flask_request.path,
            flask_request.environ.get("SERVER_PROTOCOL", "HTTP/1.1"),
            response.status_code,
            response.content_length or "-",
            elapsed,
        )
        return response

    @app.get("/health")
    def health_check():
        return "", 200

    app.register_blueprint(v1.bp, url_prefix="/v1")

    app.wsgi_app = TimeoutMiddleware(app.wsgi_app)  # ty: ignore[invalid-assignment]

    return app


def _init_http_client(app: Flask) -> None:
    settings = get_settings()
    backend = settings.backend
    cert = (str(backend.auth.cert_file), str(backend.auth.key_file))

    http_client = httpx.Client(
        base_url=backend.endpoint,
        cert=cert,
        timeout=backend.timeout,
        proxy=backend.proxy or None,
        headers={"Accept": "application/json"},
    )
    app.config["http_client"] = http_client


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, level, logging.INFO),
    )
    # Waitress has its own noisy logger -- keep it at WARNING.
    logging.getLogger("waitress").setLevel(logging.WARNING)


app = create_app()


def serve():
    settings = get_settings()
    _configure_logging(settings.logging.level)

    if settings.server.reload:
        app.run(
            host=settings.server.host,
            port=settings.server.port,
            debug=True,
        )
    else:
        logger.info(
            "Serving on http://%s:%s",
            settings.server.host,
            settings.server.port,
        )
        waitress.serve(
            app,
            host=settings.server.host,
            port=settings.server.port,
            threads=settings.server.workers * 4,
        )
