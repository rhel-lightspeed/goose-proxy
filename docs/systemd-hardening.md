# Systemd Service Hardening

goose-proxy ships a systemd unit (`goose-proxy.service`) that runs the
proxy as a system daemon.  The unit applies extensive security hardening
so that a compromise of the proxy process cannot easily escalate to the
rest of the system.

## Why the service runs as root

The proxy needs read access to two sets of root-owned files:

* **RHSM client certificates** (`/etc/pki/consumer/cert.pem` and
  `key.pem`) -- used for mTLS authentication against the backend.  The
  private key is typically `0600 root:root`.
* **Configuration file** (`/etc/xdg/goose-proxy/config.toml`) --
  installed `0600 root:root` by the RPM to prevent non-root users from
  reading potentially sensitive settings.

Running as root is the simplest way to guarantee read access to these
files.  The rest of the unit restricts what root can actually do (see
[Security directives](#security-directives) below).

## Why not DynamicUser + LoadCredential?

An earlier iteration of the unit used `DynamicUser=true` with
`LoadCredential=` to avoid running as root.  `DynamicUser` creates an
ephemeral unprivileged user, and `LoadCredential` copies the needed
files into a private `$CREDENTIALS_DIRECTORY` that the ephemeral user
can read.

This approach was abandoned for two reasons:

1. **Certificate rotation** -- `LoadCredential` copies files at service
   start.  If RHSM certificates are renewed on disk (e.g. after a
   subscription refresh), the running service keeps using the stale
   copies.  The only remedy is a full service restart.  Without
   `LoadCredential`, the proxy reads the certificates directly from
   `/etc/pki/consumer/` on every outgoing request, so rotated
   certificates are picked up automatically.

2. **Configuration accessibility** -- The config file at
   `/etc/xdg/goose-proxy/config.toml` is also unreadable by the
   ephemeral user.  Solving this would require either loading the config
   through `LoadCredential` as well (adding complexity and the same
   staleness problem) or relaxing the file permissions (defeating the
   purpose of restricting access).

## Security directives

Even though the service runs as root, the following directives ensure it
operates in a minimal, read-only sandbox:

| Directive | Effect |
|---|---|
| `ProtectSystem=strict` | Entire filesystem mounted read-only |
| `ProtectHome=true` | `/home`, `/root`, `/run/user` inaccessible |
| `PrivateTmp=true` | Isolated `/tmp` (not shared with other services) |
| `PrivateDevices=true` | Only `/dev/null`, `/dev/urandom`, `/dev/random` |
| `CapabilityBoundingSet=` | All Linux capabilities dropped |
| `NoNewPrivileges=true` | Cannot gain new privileges via execve |
| `RestrictNamespaces=true` | Cannot create new namespaces |
| `RestrictSUIDSGID=true` | Cannot create setuid/setgid binaries |
| `MemoryDenyWriteExecute=true` | Cannot allocate writable+executable memory |
| `SystemCallFilter=@system-service` | Only common service syscalls allowed |
| `ProtectKernelModules=true` | Cannot load kernel modules |
| `ProtectKernelTunables=true` | `/proc/sys`, sysctl values read-only |
| `ProtectKernelLogs=true` | No access to kernel log ring buffer |
| `ProtectClock=true` | Cannot change the system clock |
| `ProtectHostname=true` | Cannot change the hostname |
| `ProtectControlGroups=true` | cgroup filesystem read-only |
| `ProtectProc=invisible` | Only own process visible in `/proc` |
| `LockPersonality=true` | Cannot change execution domain |
| `RestrictRealtime=true` | Cannot acquire realtime scheduling |
| `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` | Only IPv4, IPv6, and Unix sockets |

The net effect is a process that can read the filesystem and open network
connections, but cannot write to disk, load modules, change the clock,
inspect other processes, or escalate privileges in any way.
