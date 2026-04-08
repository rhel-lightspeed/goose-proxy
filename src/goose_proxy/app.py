import logging
import time

import httpx

from flask import Flask
from flask import request as flask_request
from gunicorn.app.base import BaseApplication

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
    # Gunicorn has its own access logger -- keep it at WARNING so our
    # after_request hook is the single source of request logs.
    logging.getLogger("gunicorn").setLevel(logging.WARNING)


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

        class StandaloneApplication(BaseApplication):
            def __init__(self, application, options):
                self.options = options or {}
                self.application = application
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    if key in self.cfg.settings and value is not None:  # ty: ignore[unresolved-attribute]
                        self.cfg.set(key.lower(), value)  # ty: ignore[unresolved-attribute]

            def load(self):
                return self.application

        options = {
            "bind": f"{settings.server.host}:{settings.server.port}",
            "workers": settings.server.workers,
            "accesslog": None,  # Disabled; our after_request hook handles it.
        }
        logger.debug(settings.model_dump_json())
        StandaloneApplication(app, options).run()
