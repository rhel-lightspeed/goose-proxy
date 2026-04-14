# Goose Proxy

A lightweight API translation proxy that bridges [Goose](https://block.github.io/goose/) with backend servers that speak the [Responses API](https://platform.openai.com/docs/api-reference/responses), such as [Lightspeed Stack](https://github.com/lightspeed-core/lightspeed-stack).

## Overview

Goose communicates using the OpenAI Chat Completions API. The RHEL Lightspeed stack exposes the Responses API instead. Goose Proxy sits between the two, translating requests and responses on the fly so that clients and backends can each speak the format they already support.

```
┌────────┐  Chat Completions  ┌──────────────┐  Responses API  ┌───────────┐
│ Client ├───────────────────►│ goose-proxy  ├────────────────►│  Backend  │
│(Goose) │◄───────────────────┤              │◄────────────────┤ Lightspeed│
└────────┘  Chat Completions  └──────────────┘  Responses API  └───────────┘
                                    mTLS
```

Key capabilities:

- Translates messages, tools, parameters, and responses between the two API formats
- Supports both streaming (SSE) and non-streaming modes
- Authenticates to the backend with mTLS using RHSM client certificates
- Enforces configurable request timeouts
- Returns all errors in OpenAI-compatible format

## Installation

```bash
uv sync
```

## Configuration

Goose Proxy reads its configuration from a TOML file located via the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/). The default path is `/etc/xdg/goose-proxy/config.toml`.

A minimal configuration:

```toml
[backend]
endpoint = "https://lightspeed.example.com"

[backend.auth]
cert_file = "/etc/pki/consumer/cert.pem"
key_file = "/etc/pki/consumer/key.pem"
```
See [docs/man/goose-proxy-config.rst](docs/man/goose-proxy-config.rst) for the full configuration reference, or run `man goose-proxy-config` if man pages are installed.

## Usage

Start the proxy:

```bash
goose-proxy
```

Then point your OpenAI-compatible client at the proxy (default `http://127.0.0.1:7080`). For example, with curl:

```bash
curl -sX POST http://127.0.0.1:7080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "", "messages": [{"role": "user", "content": "Hello"}], "stream": false}'
```

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/)

```bash
# Install dependencies and run the dev server (auto-reload)
make dev

# Run tests
make test

# Lint and type-check
make lint
make check

# Build man pages
make man
```

A development configuration is provided in `data/development/xdg/goose-proxy/config.toml`. Point `XDG_CONFIG_DIRS` at `data/development/xdg` to use it.

## Documentation

Man pages are built with Sphinx:

```bash
make man
```

This produces:

- **goose-proxy(7)** — project overview and API translation summary
- **goose-proxy-config(5)** — configuration file reference

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
