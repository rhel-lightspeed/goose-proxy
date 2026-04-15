===========
Goose Proxy
===========

SYNOPSIS
========

**goose-proxy**

DESCRIPTION
===========

**goose-proxy** is an API translation proxy that sits between OpenAI-compatible
clients (such as the Goose AI agent) and a backend that speaks the Responses API
(such as RHEL Lightspeed).

Goose and many other AI tooling clients speak the OpenAI Chat Completions API.
The RHEL Lightspeed stack exposes the Responses API instead. **goose-proxy**
bridges this gap by accepting Chat Completions requests, translating them into
Responses API calls, forwarding them to the backend over mTLS, and translating
the results back into the Chat Completions format the client expects.

Both streaming (Server-Sent Events) and non-streaming request modes are
supported.

API TRANSLATION
===============

**goose-proxy** exposes the following endpoints:

``POST /v1/chat/completions``
    The main proxy endpoint. Accepts an OpenAI Chat Completions request body and
    returns a Chat Completions response. The request is translated to the
    Responses API format before being forwarded to the backend; the backend
    response is translated back before being returned to the client.

``GET /v1/models``
    Returns the list of available models. Currently returns a single hardcoded
    model identifier (``rhel-lightspeed/goose``) to avoid unnecessary backend
    round-trips.

``GET /health``
    Health check endpoint for infrastructure probes. Returns an empty 200
    response.

The following Chat Completions features are translated:

- **System messages** are concatenated into the Responses API ``instructions``
  field.
- **User messages** (text and images) become ``message`` input items.
- **Assistant messages** are split into ``message`` and ``function_call`` items
  as appropriate.
- **Tool messages** become ``function_call_output`` items.
- **Tool definitions and tool_choice** are mapped to their Responses API
  equivalents.
- **Parameters** such as ``temperature``, ``max_tokens`` (renamed to
  ``max_output_tokens``), and ``stream`` are forwarded.

AUTHENTICATION
==============

**goose-proxy** authenticates to the backend using mutual TLS (mTLS) with
client certificates issued by RHSM (Red Hat Subscription Manager). The
certificate and key paths are configured in the ``[backend.auth]`` section of
the configuration file. See **goose-proxy-config**\(5) for details.

CONFIGURATION
=============

**goose-proxy** reads its configuration from a TOML file located via the XDG
Base Directory Specification. The default path is
``/etc/xdg/goose-proxy/config.toml``. See **goose-proxy-config**\(5) for a
complete reference of all configuration options.

SOCKET ACTIVATION
=================

When installed as a system package, **goose-proxy** is socket-activated by
systemd. The ``goose-proxy.socket`` unit listens on ``127.0.0.1:7080`` and
starts the service on demand when a client connects.

To enable the socket::

    systemctl enable --now goose-proxy.socket

The service detects socket activation automatically via the ``LISTEN_FDS``
environment variable and uses the passed file descriptor instead of binding
to the configured host and port.

SEE ALSO
========

**goose-proxy-config**\(5)

Project repository: https://github.com/rhel-lightspeed/goose-proxy
