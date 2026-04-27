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

PYTHON_VERSIONS=("3.9" "3.12")
ARCHES=("x86_64" "aarch64" "s390x" "ppc64le")

cd "$PROJECT_ROOT"

# Ensure deterministic output when the workspace is reused.
rm -rf vendor_wheels
mkdir -p vendor_wheels
mkdir -p "$(dirname "$OUTPUT")"

for python_version in "${PYTHON_VERSIONS[@]}"
do
    # Resolve dependencies for each target Python version. Python 3.9 (RHEL 9)
    # and 3.12 (RHEL 10) have different dependency constraints (e.g. typer
    # requires click>=8.2.1 only on Python 3.10+, but click 8.2.x dropped
    # Python 3.9 support).
    uv pip compile pyproject.toml \
        --python-version ${python_version} \
        -c packaging/constraints.txt \
        --no-header --no-annotate \
        -o "requirements-${python_version/./}.txt"

    for arch in "${ARCHES[@]}"
    do
        for attempt in 1 2 3
        do
            # Download binary wheels for each Python version and architecture.
            # --no-deps is required because pip evaluates environment markers
            # using the host Python, not the target version set by
            # --python-version, causing false dependency conflicts.
            pip3 download --no-deps --dest vendor_wheels --only-binary=:all: \
                --python-version ${python_version} --abi cp${python_version/./} --implementation cp \
                --platform "manylinux_2_17_${arch}" --platform "manylinux_2_28_${arch}" \
                -r "requirements-${python_version/./}.txt" && break
            echo "Attempt ${attempt} for ${arch} failed. Retrying..."
            sleep 5
        done
    done

    # Bundle requirements files so the spec can select the right one at build
    # time based on the target Python version.
    mv requirements-${python_version/./}.txt vendor_wheels
done

tar czf "$OUTPUT" vendor_wheels/

# Cleanup the root vendor_wheels directory.
rm -rf vendor_wheels

echo "Created $OUTPUT"
