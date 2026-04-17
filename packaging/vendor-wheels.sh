#!/usr/bin/bash
# Generate the vendored wheels tarball for RHEL 9 (Python 3.9) and RHEL 10
# (Python 3.12). Used by both the GitHub Actions release workflow and packit
# post-upstream-clone actions.
#
# Requirements: uv, pip3
# Output: packaging/vendor-wheels.tar.gz (or $OUTPUT if set)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT="${OUTPUT:-$PROJECT_ROOT/packaging/vendor-wheels.tar.gz}"

cd "$PROJECT_ROOT"

# Ensure deterministic output when the workspace is reused.
rm -rf vendor_wheels
mkdir -p vendor_wheels
mkdir -p "$(dirname "$OUTPUT")"

# Resolve dependencies separately for each target Python version.
# Python 3.9 (RHEL 9) and 3.12 (RHEL 10) have different dependency
# constraints (e.g. typer requires click>=8.2.1 only on Python 3.10+,
# but click 8.2.x dropped Python 3.9 support).
uv pip compile pyproject.toml \
    --python-version 3.9 \
    -c packaging/constraints.txt \
    --no-header --no-annotate \
    -o requirements-39.txt

uv pip compile pyproject.toml \
    --python-version 3.12 \
    -c packaging/constraints.txt \
    --no-header --no-annotate \
    -o requirements-312.txt

# Download binary wheels for each Python version.
# --no-deps is required because pip evaluates environment markers using
# the host Python, not the target version set by --python-version,
# causing false dependency conflicts.
pip3 download --no-deps --dest vendor_wheels --only-binary=:all: \
    --python-version 3.9 --abi cp39 --implementation cp \
    --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    -r requirements-39.txt

pip3 download --no-deps --dest vendor_wheels --only-binary=:all: \
    --python-version 3.12 --abi cp312 --implementation cp \
    --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    -r requirements-312.txt

# Bundle requirements files so the spec can select the right one at
# build time based on the target Python version.
cp requirements-39.txt requirements-312.txt vendor_wheels/

tar czf "$OUTPUT" vendor_wheels/

echo "Created $OUTPUT"
