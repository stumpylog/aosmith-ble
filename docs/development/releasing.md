# Releasing

The version lives in one place, `version` in `pyproject.toml`. `aosmith_ble.__version__` reads it from the installed package metadata.

To release:

1. Set the new `version` in `pyproject.toml`. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [<version>] - <YYYY-MM-DD>`, add a fresh empty `## [Unreleased]` above it, and update the link references at the bottom: `[Unreleased]` compares the new tag to `HEAD`, and the new version compares the previous tag to the new one. That section becomes the GitHub release notes, and the release fails before anything is built if it is missing or empty.

The changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Record changes under `## [Unreleased]` as they land, grouped under `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed` or `### Security`. The lint job checks the format on every push, and the same check runs as a prek hook.

2. Merge to `main` with the tests, lint and docs jobs green.
3. Tag the merge commit `v<version>` (for example `v0.1.0`) and push the tag.

The release workflow then checks that the tag matches `pyproject.toml`, runs the tests, builds the sdist and wheel, smoke-tests the wheel in a clean environment, and publishes to PyPI. Once PyPI has accepted the upload, it creates the GitHub release for the tag, with the changelog section as its notes and the sdist and wheel attached. A tag that does not match the version fails before anything is built.

Publishing uses PyPI trusted publishing, so no API token is stored in the repository. The PyPI project trusts the `release.yml` workflow running in the `pypi` GitHub environment.

!!! warning
    A version published to PyPI can be yanked but never replaced. Check the built files before tagging, and use a new version number for any fix.
