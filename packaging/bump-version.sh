#!/usr/bin/env bash
# Bump the goose-proxy version in every file that must stay in sync.
# Usage: packaging/bump-version.sh X.Y.Z
set -euo pipefail

VERSION="${1:-}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Usage: $0 X.Y.Z (semantic version, e.g. 1.1.0)" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

sed -i -E "s/^(Version:[[:space:]]+).*/\1${VERSION}/" "$ROOT/packaging/goose-proxy.spec"
sed -i -E "s/^(__version__ = \").*(\")/\1${VERSION}\2/" "$ROOT/src/goose_proxy/__init__.py"
sed -i -E "s/^(policy_module\(goose_proxy, ).*(\))/\1${VERSION}\2/" "$ROOT/data/release/selinux/goose_proxy.te"

echo "Bumped to ${VERSION}:"
grep -n "^Version:" "$ROOT/packaging/goose-proxy.spec"
grep -n "^__version__" "$ROOT/src/goose_proxy/__init__.py"
grep -n "^policy_module" "$ROOT/data/release/selinux/goose_proxy.te"
