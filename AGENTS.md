# AGENTS.md - goose-proxy

FastAPI passthrough proxy for the OpenAI Responses API with RHEL Lightspeed. Authenticates to the backend via RHSM client certificates (mTLS). Supports streaming (SSE) and non-streaming modes.

## Build & Run

```bash
uv sync --locked   # install all deps (including dev)
make dev           # run server (127.0.0.1:7080, defaults from config.toml)
```

## CI Commands (Makefile)

```bash
make sanity      # full suite: lint + typecheck + format
make lint        # ruff check src/ tests/
make format      # ruff format src/ tests/
make type        # ty check src/
make test        # pytest with coverage
make dev         # fastapi dev server (auto-reload)
make man         # build Sphinx man pages
make request     # curl test request to localhost:7080
make clean       # remove build artifacts and caches
```

## Running Tests

```bash
make test                                  # all tests
uv run pytest tests/test_v1.py             # single file
uv run pytest tests/test_v1.py::test_name  # single test
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| Change error handling | `src/goose_proxy/exceptions.py` | Must follow OpenAI error format; catches `openai.*` exceptions |
| Modify config/settings | `src/goose_proxy/config.py` | Add field to `Backend`, `Server`, or `Logging`; parsed from TOML |
| Adjust timeout behavior | `src/goose_proxy/middleware.py` | `TimeoutMiddleware`: ASGI middleware, streaming-safe |
| CI/CD workflows | `.github/workflows/` | `ci.yml` (test+lint), `release-vendor.yml` (vendor tarball) |
| Man pages | `docs/man/` | Sphinx RST; build with `make man` |

## Boot Sequence

```text
goose-proxy
  → pyproject.toml: goose-proxy = "goose_proxy.cli:serve"
  → cli.py: serve()
       ├─ get_settings()           # parse XDG config.toml via pydantic
       ├─ _is_socket_activated()   # check LISTEN_FDS / LISTEN_PID
       └─ uvicorn.run(app, ...)    # start ASGI server (fd= or host:port)
           → app.py: FastAPI()
               ├─ TimeoutMiddleware
               ├─ register_exception_handlers()
               ├─ /health endpoint
               └─ v1.router (/v1/responses, /v1/models)
```

## Request Flow

```text
Client (Goose) → POST /v1/responses
  → request.json() (raw body passthrough)
  → _build_client() (mTLS via httpx.AsyncClient)
  ├─ [stream=false] → client.post(url, json=body)
  └─ [stream=true]  → client.send(req, stream=True) + status check before committing headers
```

## Vendoring

Runtime dependencies are vendored into `src/goose_proxy/_vendor/` for RPM packaging (RHEL ships without pip/PyPI access). The `_vendor/__init__.py` injects the vendor path into `sys.path`. See `docs/packaging.md` for the full strategy and `packaging/vendor-wheels.sh` for the download script.

## Documentation

When a change is large or unconventional — a new architectural pattern, a non-obvious design decision, a significant refactor — add a markdown file in `docs/` explaining the purpose and reasoning. Existing examples: `docs/packaging.md` (vendoring strategy), `docs/systemd-hardening.md` (security rationale), `docs/api-translation.md` (format mapping reference). The goal is to capture *why* something was done so future contributors don't have to reverse-engineer intent from code alone.
