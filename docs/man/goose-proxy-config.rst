===================
goose-proxy-config
===================

SYNOPSIS
========

``/etc/xdg/goose-proxy/config.toml``

DESCRIPTION
===========

The **goose-proxy** configuration file is a TOML file that controls server
behavior, backend connectivity, authentication, and logging.

**goose-proxy** locates its configuration file using the XDG Base Directory
Specification. It checks the directories listed in ``$XDG_CONFIG_DIRS``
(colon-separated) for a file named ``goose-proxy/config.toml``. If
``$XDG_CONFIG_DIRS`` is unset, the default path ``/etc/xdg`` is used, resulting
in ``/etc/xdg/goose-proxy/config.toml``.

All sections and keys are optional. When a key is omitted, the documented
default value is used.

SECTIONS
========

[server]
--------

Settings that control the HTTP server (uvicorn).

.. note::

   Under systemd socket activation, the ``host`` and ``port`` settings are
   ignored. The listening address is controlled by the ``goose-proxy.socket``
   unit file instead.

``host`` = *string*
    The address to bind the server to.
    **Default:** ``"127.0.0.1"``

``port`` = *integer*
    The port to listen on.
    **Default:** ``7080``

``reload`` = *boolean*
    Enable automatic reloading when source files change. Intended for
    development use only.
    **Default:** ``false``

``workers`` = *integer*
    Number of uvicorn worker processes.
    **Default:** ``1``

[backend]
---------

Settings for communicating with the upstream Responses API server.

``endpoint`` = *string*
    The base URL of the backend API server.
    **Default:** ``"https://cert.console.redhat.com/api/lightspeed/v1"``

``timeout`` = *integer*
    HTTP request timeout in seconds. This timeout covers only the initial
    response from the backend; once response headers arrive, the timeout is
    lifted to allow long-running streaming responses to complete.
    **Default:** ``30``

``proxy`` = *string*
    An optional HTTP proxy URL to route backend requests through. Supports
    ``username:password@host:port`` syntax for authenticated proxies.
    **Default:** ``""`` (no proxy)

[backend.auth]
--------------

Mutual TLS (mTLS) authentication settings for the backend connection. The
certificate and key are typically issued by RHSM (Red Hat Subscription
Manager).

``cert_file`` = *string*
    Path to the PEM-encoded client certificate file.
    **Default:** ``"/etc/pki/consumer/cert.pem"``

``key_file`` = *string*
    Path to the PEM-encoded client private key file.
    **Default:** ``"/etc/pki/consumer/key.pem"``

[logging]
---------

Logging configuration.

``level`` = *string*
    The log level. Must be one of: ``CRITICAL``, ``ERROR``, ``WARNING``,
    ``INFO``, ``DEBUG``, ``NOTSET``. The value is case-insensitive.
    **Default:** ``"INFO"``

EXAMPLE
=======

A minimal production configuration::

    [backend]
    endpoint = "https://lightspeed.example.com"
    timeout = 60

    [backend.auth]
    cert_file = "/etc/pki/consumer/cert.pem"
    key_file = "/etc/pki/consumer/key.pem"

    [logging]
    level = "WARNING"

SEE ALSO
========

**goose-proxy**\(7)

Project repository: https://github.com/rhel-lightspeed/goose-proxy
