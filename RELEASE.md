# Releasing goose-proxy

Every release is cut from its own dedicated branch, created from `main`.

## Versioning

goose-proxy follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

| Bump | Example | When |
|------|---------|------|
| **Major** | `1.4.2` -> `2.0.0` | Breaking changes: removed or renamed config options, changed CLI/API behavior that existing users or the RPM's systemd/SELinux setup rely on. |
| **Minor** | `1.4.2` -> `1.5.0` | Backwards-compatible new functionality (new config option, new supported endpoint or feature). |
| **Bugfix (patch)** | `1.4.2` -> `1.4.3` | Backwards-compatible fixes: bug fixes, dependency/security updates, packaging or SBOM fixes. |

## Release steps

1. Create a release branch from an up-to-date `main`, e.g. `release-1.1.0`:

   ```bash
   git checkout main && git pull
   git checkout -b release-1.1.0
   ```

2. Bump the version in **all** of these places (they must match):
   - `Version:` in `packaging/goose-proxy.spec`
   - `__version__` in `src/goose_proxy/__init__.py`
   - `policy_module(goose_proxy, X.Y.Z)` in `data/release/selinux/goose_proxy.te`

3. If dependencies changed, update the static `Provides: bundled()` list in
   `packaging/goose-proxy.spec` (keep it in sync with
   `uv pip compile pyproject.toml`).

4. Run `make sanity` and `make test`, then open a PR from the release branch
   into `main` and get it reviewed and merged.

5. Tag the release as `vX.Y.Z` and publish a GitHub release for that tag.
   Publishing it triggers `.github/workflows/release-vendor.yml`, which builds
   and uploads `vendor-wheels.tar.gz` to the release. The spec's `Source` and
   `Source1` URLs point at `v%{version}`, so the tag and the `Version:` field
   must match exactly.

## RPM upgrade

Cutting a new release triggers an automatic upgrade of the `goose-proxy` RPM
package: the new `Version:` in the spec produces a new package version built
from that release's source tarball and vendor tarball. Because of this, never
bump the version in regular feature or fix PRs; only release branches change it.
