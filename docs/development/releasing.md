# Releasing

The version lives in one place, `version` in `pyproject.toml`. `aosmith_ble.__version__` reads it from the installed package metadata.

To release:

1. Set the new `version` in `pyproject.toml` and move the `CHANGELOG.md` entries under that version.
2. Merge to `main` with the tests, lint and docs jobs green.
3. Tag the merge commit `v<version>` (for example `v0.1.0`) and push the tag.

The release workflow then checks that the tag matches `pyproject.toml`, runs the tests, builds the sdist and wheel, smoke-tests the wheel in a clean environment, and publishes to PyPI. A tag that does not match the version fails before anything is built.

Publishing uses PyPI trusted publishing, so no API token is stored in the repository. The PyPI project trusts the `release.yml` workflow running in the `pypi` GitHub environment.

!!! warning
    A version published to PyPI can be yanked but never replaced. Check the built files before tagging, and use a new version number for any fix.
