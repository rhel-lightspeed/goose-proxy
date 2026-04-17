# RPM Packaging

goose-proxy is packaged as an RPM for RHEL 9 and RHEL 10. Because the runtime
dependencies (fastapi, pydantic, uvicorn, etc.) are not available in
the RHEL base repositories, they are **vendored** as prebuilt wheels and
shipped inside the package itself.

This document explains how the packaging pipeline works and the reasoning
behind each non-obvious decision.

## Overview

The build pipeline has two stages:

1. **SRPM creation** (Fedora, orchestrated by Packit) -- resolves
   dependencies, downloads wheels, and bundles them into the SRPM.
2. **RPM build** (RHEL mock chroot) -- installs vendored wheels into the
   source tree, builds the project wheel, and installs everything into the
   RPM buildroot.

```text
pyproject.toml
     |
     v
 uv pip compile          pip3 download
 (per Python version) --> (per Python version)
     |                         |
     v                         v
 requirements-39.txt      vendor_wheels/
 requirements-312.txt         |
                              v
                     vendor-wheels.tar.gz  (Source1)
                              |
                              v
                     RPM build (%prep / %build / %install)
```

## Vendoring strategy

All Python runtime dependencies are installed into
`src/goose_proxy/_vendor/` during `%prep`. This directory is part of the
goose_proxy package, so it is included in the wheel produced by
`%py3_build_wheel` and ends up under
`%{python3_sitelib}/goose_proxy/_vendor/` in the installed RPM.

At runtime, `goose_proxy/_vendor/__init__.py` prepends the `_vendor`
directory to `sys.path`, making vendored packages importable through
normal `import` statements while taking priority over any system-installed
versions.

## Why per-version requirements files?

RHEL 9 ships Python 3.9; RHEL 10 ships Python 3.12. Several packages have
different dependency constraints across these versions:

- **click**: `typer` requires `click >= 8.2.1` only on Python 3.10+
  (`python_version >= "3.10"` marker). Click 8.2.x dropped Python 3.9
  support, so Python 3.9 must stay on Click 8.1.x while Python 3.12 uses
  8.2.x+.
- **httptools**: version 0.7+ stopped publishing prebuilt `cp39` wheels.
  `packaging/constraints-39.txt` pins `httptools < 0.7` so `uv` resolves
  to 0.6.4 for Python 3.9.

`uv pip compile` resolves the full transitive dependency tree correctly for
each Python version, producing `requirements-39.txt` and
`requirements-312.txt`.

## Why `--no-deps` on `pip download`?

`pip download --python-version 3.9` runs on the Fedora SRPM-build host
(Python 3.14). The `--python-version` flag controls which **wheel tags**
pip selects (e.g. `cp39`), but pip evaluates `python_version` environment
markers using the **host** interpreter. This causes pip to see
`typer -> click >= 8.2.1; python_version >= "3.10"` as active (3.14 >= 3.10)
and conflict with the correctly-pinned `click == 8.1.8`.

Since `uv pip compile` already resolved every transitive dependency, pip
only needs to fetch the matching wheels. `--no-deps` skips the broken
cross-version dependency resolution entirely.

## Why two `--platform` flags?

Some packages publish wheels under `manylinux_2_17` tags, others under
`manylinux_2_28`. Both glibc levels are supported by RHEL 9 (glibc 2.34)
and RHEL 10 (glibc 2.39). Specifying both platforms ensures pip finds a
wheel regardless of which tag the upstream project chose.

## setup.py compatibility shim

RHEL 9 ships setuptools < 61, which cannot read the `[project]` table from
`pyproject.toml` (PEP 621). The `setup.py` at the repository root reads
`pyproject.toml` with `tomllib`/`tomli` and passes the metadata to
`setup()`, so the same source works on both old and new setuptools.

RHEL 9 builds require `python3-tomli` (backport of `tomllib`); on
Python 3.11+ the standard library module is used.

## Spec file details

### `%global debug_package %{nil}`

Vendored `pydantic_core` ships prebuilt `.so` files. These binaries lack
debug sources, causing `rpmbuild` to fail with an empty
`debugsourcefiles.list`. Disabling debuginfo generation avoids this.

### `%{?python_disable_dependency_generator}`

All runtime Python dependencies are vendored. Without this macro, RPM's
automatic dependency generator would add
`Requires: python3.Xdist(fastapi)`, etc., which do not exist as system
packages on RHEL. The macro disables automatic Python `Requires`
generation.

### `fix-spec-file` Packit action

The spec declares `Source1` as a GitHub release URL for tagged releases.
During PR and main-branch Copr builds, the vendor tarball is generated
locally by the `post-upstream-clone` actions. The `fix-spec-file` action
rewrites `Source1` to the local filename so Packit uses the generated
tarball instead of attempting (and failing) to download a non-existent
release artifact.

## Adding or updating a vendored dependency

1. Update the dependency in `pyproject.toml`.
2. If the new version lacks prebuilt `cp39` wheels, add a constraint to
   `packaging/constraints-39.txt`.
3. Push a PR -- Packit will regenerate the requirements files and vendor
   tarball automatically.
4. For tagged releases, attach the `vendor-wheels.tar.gz` artifact to the
   GitHub release.
