"""scripts/changelog_section.py: the release notes for one version."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "changelog_section", ROOT / "scripts" / "changelog_section.py"
)
changelog_section = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog_section)

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Not released yet.

## [0.3.0] - 2026-11-01

### Added

- New thing.

### Fixed

- Another thing.

## [0.2.10] - 2026-10-30

### Added

- Not this one.

## [0.2.1] - 2026-10-20

### Added

- Last section.

[Unreleased]: https://example.invalid/compare/v0.3.0...HEAD
[0.3.0]: https://example.invalid/compare/v0.2.10...v0.3.0
"""


def test_returns_the_body_of_the_requested_section():
    assert changelog_section.section(CHANGELOG, "0.3.0") == (
        "### Added\n\n- New thing.\n\n### Fixed\n\n- Another thing.\n"
    )


def test_a_version_prefix_does_not_match_a_longer_version():
    assert (
        changelog_section.section(CHANGELOG, "0.2.1")
        == "### Added\n\n- Last section.\n"
    )


def test_the_last_section_stops_before_the_link_references():
    assert "example.invalid" not in changelog_section.section(CHANGELOG, "0.2.1")


def test_unreleased_is_not_a_version():
    with pytest.raises(changelog_section.ChangelogError):
        changelog_section.section(CHANGELOG, "Unreleased")


def test_a_missing_section_raises():
    with pytest.raises(changelog_section.ChangelogError, match="0.9.0"):
        changelog_section.section(CHANGELOG, "0.9.0")


def test_an_empty_section_raises():
    text = "# Changelog\n\n## [0.1.0] - 2026-10-09\n\n## [0.0.9] - 2026-10-01\n"
    with pytest.raises(changelog_section.ChangelogError, match="empty"):
        changelog_section.section(text, "0.1.0")


def test_a_leading_v_is_accepted():
    assert changelog_section.section(CHANGELOG, "v0.3.0").startswith("### Added")


def test_the_real_changelog_has_a_section_for_the_current_version():
    import tomllib

    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    changelog_section.section((ROOT / "CHANGELOG.md").read_text(), version)
