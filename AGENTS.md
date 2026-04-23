# AGENTS.md - goose-proxy

FastAPI proxy translating OpenAI Chat Completions API requests to the Responses API for RHEL Lightspeed. Authenticates to the backend via RHSM client certificates (mTLS). Supports streaming (SSE) and non-streaming modes.

## Maintenance Rule

After any code change, verify that this file is still accurate. Update it in the same PR if anything has drifted: new modules, changed function signatures, removed features, renamed files, new dependencies, etc.

## Build & Run

```bash
uv sync                      # install all deps (including dev)
uv run goose-proxy           # run server (127.0.0.1:7080, defaults from config.toml)
```

Configuration is read from `$XDG_CONFIG_DIRS/goose-proxy/config.toml` (defaults to `/etc/xdg/goose-proxy/config.toml`). Missing config file is fine — all settings have sensible defaults.

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
uv run pytest                              # all tests
uv run pytest tests/test_v1.py             # single file
uv run pytest tests/test_v1.py::test_name  # single test
uv run pytest -k "timeout"                 # by keyword
uv run pytest -x                           # stop on first failure
uv run pytest -v --cov=src --cov-report=term-missing  # with coverage (same as `make test`)
```

pytest is configured with `asyncio_mode = "auto"` so async tests run without explicit event loop setup.

## Project Layout

```text
src/goose_proxy/
  __init__.py         # vendor setup (imports _vendor)
  app.py              # FastAPI application, middleware, exception handlers, /health endpoint
  cli.py              # CLI entrypoint (goose-proxy), uvicorn runner, systemd socket activation
  config.py           # Settings (pydantic BaseModel), XDG config path, TOML parsing
  exceptions.py       # GooseProxyError hierarchy, OpenAI-compatible error response builders
  middleware.py       # TimeoutMiddleware: enforces backend response timeout (streaming-safe)
  v1.py               # /v1 router: BackendClient (mTLS via urllib), /chat/completions, /models
  models/
    __init__.py
    chat.py            # Chat Completions API models (request + response)
    responses.py       # Responses API models (response + stream events)
  translators/
    __init__.py        # re-exports translate_request, translate_response, translate_stream
    request.py         # Chat Completions → Responses API (messages, tools, tool_choice)
    response.py        # Responses API → Chat Completions (output items → choices)
    streaming.py       # SSE chunk translation (Responses stream → Chat Completions deltas)
  _vendor/
    __init__.py        # sys.path manipulation for vendored packages
    ...                # vendored runtime deps (for RPM packaging)
tests/
  conftest.py                  # shared fixtures
  test_cli.py                  # CLI and socket activation tests
  test_config.py               # Settings, XDG path, TOML parsing tests
  test_exceptions.py           # error handler tests
  test_middleware.py           # timeout middleware tests
  test_models.py               # Pydantic model validation tests
  test_v1.py                   # route handler + BackendClient tests
  test_vendor.py               # vendor path setup tests
  translators/
    test_request.py            # request translation tests
    test_response.py           # response translation tests
    test_streaming.py          # streaming translation tests
docs/
  api-translation.md           # detailed API format mapping reference
  testing.md                   # backend connectivity & endpoint testing
  packaging.md                 # RPM vendoring strategy
  systemd-hardening.md         # systemd security hardening docs
  man/                         # Sphinx RST man pages (goose-proxy, goose-proxy-config)
packaging/
  goose-proxy.spec             # RPM spec file (RHEL 9/10)
  vendor-wheels.sh             # download vendored wheels script
  constraints.txt              # dependency constraints for vendoring
data/
  development/xdg/goose-proxy/ # dev config (config.toml for local development)
  release/                     # release config templates
.github/
  CODEOWNERS                   # PR review assignment (@rhel-lightspeed/developers)
  workflows/
    ci.yml                     # CI: lint, format, typecheck, pytest matrix (3.9–3.14t)
    release-vendor.yml         # vendor tarball release workflow
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| Add a new API endpoint | `src/goose_proxy/v1.py` | Add route to `router`; models go in `models/` |
| Change request translation | `src/goose_proxy/translators/request.py` | Chat Completions → Responses API mapping |
| Change response translation | `src/goose_proxy/translators/response.py` | Responses API → Chat Completions mapping |
| Change streaming translation | `src/goose_proxy/translators/streaming.py` | SSE event-by-event translation |
| Add/modify Pydantic models | `src/goose_proxy/models/chat.py`, `models/responses.py` | Chat Completions and Responses API models |
| Change error handling | `src/goose_proxy/exceptions.py` | Must follow OpenAI error format |
| Modify config/settings | `src/goose_proxy/config.py` | Add field to `Backend`, `Server`, or `Logging`; parsed from TOML |
| Adjust timeout behavior | `src/goose_proxy/middleware.py` | `TimeoutMiddleware`: ASGI middleware, streaming-safe |
| Backend HTTP client | `src/goose_proxy/v1.py` (`BackendClient`) | mTLS via `ssl.SSLContext`, uses `urllib.request` |
| Systemd socket activation | `src/goose_proxy/cli.py` | sd_listen_fds protocol |
| RPM packaging | `packaging/goose-proxy.spec` | Spec must match `pyproject.toml` versions |
| Vendoring deps | `packaging/vendor-wheels.sh`, `src/goose_proxy/_vendor/` | See `docs/packaging.md` |
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
               └─ v1.router (/v1/chat/completions, /v1/models)
```

## Request Flow

```text
Client (Goose) → POST /v1/chat/completions
  → ChatCompletionRequest (pydantic validation)
  → BackendClient.create() (mTLS ssl context)
  → translate_request() (Chat Completions → Responses API)
  ├─ [stream=false] → client.create_response() → translate_response() → ChatCompletion
  └─ [stream=true]  → client.open_stream() → translate_stream() → SSE chunks
```

## Module Dependencies

```text
__init__.py → _vendor (side-effect import for sys.path)
cli.py → app, config
app.py → v1, exceptions, middleware
v1.py → config, exceptions, models/chat, models/responses, translators
translators/__init__.py → translators/request, translators/response, translators/streaming
translators/request.py → models/chat
translators/response.py → models/chat, models/responses
translators/streaming.py → models/responses
middleware.py → config
exceptions.py → (standalone, uses fastapi + urllib.error)
config.py → (standalone, uses pydantic + tomllib)
models/chat.py → (standalone, uses pydantic)
models/responses.py → (standalone, uses pydantic)
```

No circular imports. Models have zero internal dependencies.

## Code Style

### Python Version & Formatting
- **Target**: Python 3.9+ (CI tests 3.9 through 3.14, including 3.14t free-threaded)
- **Line length**: 120 characters
- **Formatter**: ruff format
- **Linter**: ruff check with rules: E, F, I (isort), C90 (complexity), RUF100 (unused noqa), T20 (print)
- **Max complexity**: 12 (mccabe)

### RHEL Compatibility
- Python 3.9 is the floor (RHEL 9). No walrus operators in complex expressions, no `match`/`case`, no `type` statement, no `ExceptionGroup`.
- Use `typing.Union` / `typing.Optional` instead of `X | Y` syntax for type hints in runtime code.
- `tomli` is vendored for Python <3.11 compatibility (`tomllib` is stdlib from 3.11+).

### Imports
- Order: stdlib, third-party, relative (enforced by ruff `I` rule)
- Force single-line imports (ruff isort config)
- Side-effect imports get a `noqa` comment explaining why:
  ```python
  import goose_proxy._vendor  # noqa: F401
  ```

### Type Hints
- Type checker: `ty` (not mypy/pyright)
- Target Python version for ty: 3.9
- Use pydantic `Field()` with descriptions for config models
- Use `field_validator` for value normalization

### Naming
- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- Prefix private/internal functions with `_` (e.g., `_translate_messages`)
- Constants in `UPPER_SNAKE_CASE`

### Docstrings
- PEP 257 style on every module, class, and function
- Module docstrings are single-line: `"""Description of the module."""`
- Test docstrings describe the behavior being verified, not the test name

### Error Handling
- All error responses must follow OpenAI's error format: `{"error": {"message": ..., "type": ..., "code": ...}}`
- Use the `_openai_error_response()` builder in `exceptions.py`
- Register new exception handlers in `register_exception_handlers()`
- Use specific exception types (`urllib.error.HTTPError`, not bare `Exception`)
- Log with `logger.debug()` for backend details, `logger.warning()` for expected failures

### Async
- Route handlers are `async` (FastAPI convention)
- Backend HTTP uses synchronous `urllib.request` (not httpx/aiohttp) — runs in threadpool via FastAPI
- pytest asyncio_mode is `auto`, so no `@pytest.mark.asyncio` needed

### Security Suppressions
- Always add the rationale after noqa comments

## Configuration Pattern

Config uses pydantic `BaseModel` (not `BaseSettings`) with TOML file parsing. Path: `$XDG_CONFIG_DIRS/goose-proxy/config.toml`. Settings are cached via `@lru_cache`. Three sections: `[backend]` (endpoint, auth, proxy, timeout), `[server]` (host, port, reload, workers), `[logging]` (level).

Auth uses RHSM certificates at `/etc/pki/consumer/{cert,key}.pem` by default.

## Testing Patterns

- **Coverage target**: Aim for 100% coverage of new code introduced in the branch. But coverage alone is not the goal — every test must be meaningful. Don't write tests just to hit a coverage number; write tests that verify actual behavior, validate that a bug fix prevents regression, or confirm that a feature works end-to-end. A test that exercises a code path without asserting anything useful is worse than no test — it gives false confidence.
- **HTTP mocking**: Tests mock `urllib.request` / `urllib.response` (not httpx)
- **Fixtures**: shared in `conftest.py`, test-local when specific
- **Parametrize**: use `@pytest.mark.parametrize` for value variations
- **Mocking**: `unittest.mock.patch` / `patch.dict` for env vars and SSL
- **Assert style**: direct assertions, `pytest.raises` for expected errors
- **Coverage**: HTML reports in `coverage/htmlcov/`, branch coverage enabled

## Vendoring

Runtime dependencies are vendored into `src/goose_proxy/_vendor/` for RPM packaging (RHEL ships without pip/PyPI access). The `_vendor/__init__.py` injects the vendor path into `sys.path`. See `docs/packaging.md` for the full strategy and `packaging/vendor-wheels.sh` for the download script.

## Documentation

When a change is large or unconventional — a new architectural pattern, a non-obvious design decision, a significant refactor — add a markdown file in `docs/` explaining the purpose and reasoning. Existing examples: `docs/packaging.md` (vendoring strategy), `docs/systemd-hardening.md` (security rationale), `docs/api-translation.md` (format mapping reference). The goal is to capture *why* something was done so future contributors don't have to reverse-engineer intent from code alone.

## Pre-PR Code Review

Before creating a pull request, check if `coderabbit` is available in `$PATH`. If it is, ask the user whether they'd like a CodeRabbit review before opening the PR. Run it with structured output for easy parsing:

```bash
coderabbit review --agent --base <base-branch> -c .coderabbit.yaml
```

The CLI does not auto-read `.coderabbit.yaml` from the repo root. Always pass `-c .coderabbit.yaml` so local reviews match the GitHub PR review behavior (tone, path instructions, review profile).

If findings come back, address them before creating the PR (or flag them for the user). Zero findings means good to go.
