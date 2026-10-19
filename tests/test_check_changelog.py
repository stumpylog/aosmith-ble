"""scripts/check_changelog.py: CHANGELOG.md follows Keep a Changelog."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_changelog", ROOT / "scripts" / "check_changelog.py"
)
check_changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_changelog)

URL = "https://github.com/stumpylog/aosmith-ble"

VALID = f"""# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.2.0] - 2026-10-19

### Added

- A thing.

### Fixed

- A bug.

## [0.1.0] - 2026-10-09

### Added

- The first thing.

[Unreleased]: {URL}/compare/v0.2.0...HEAD
[0.2.0]: {URL}/compare/v0.1.0...v0.2.0
[0.1.0]: {URL}/releases/tag/v0.1.0
"""


def problems(text: str) -> list[str]:
    return check_changelog.validate(text)


def test_a_valid_changelog_has_no_problems():
    assert problems(VALID) == []


def test_the_real_changelog_is_valid():
    assert problems((ROOT / "CHANGELOG.md").read_text()) == []


def test_the_title_is_required():
    assert any("# Changelog" in p for p in problems(VALID.replace("# Changelog\n", "")))


def test_unreleased_must_be_the_first_section():
    text = VALID.replace("## [Unreleased]\n\n", "")
    assert any("Unreleased" in p for p in problems(text))


def test_a_release_heading_needs_a_valid_date():
    text = VALID.replace("## [0.2.0] - 2026-10-19", "## [0.2.0] - 2026-13-01")
    assert any("0.2.0" in p and "date" in p for p in problems(text))


def test_a_release_heading_without_a_date_is_rejected():
    text = VALID.replace("## [0.2.0] - 2026-10-19", "## [0.2.0]")
    assert any("0.2.0" in p for p in problems(text))


def test_versions_must_be_newest_first():
    text = VALID.replace("[0.2.0] - 2026-10-19", "[0.0.9] - 2026-10-19").replace(
        "[0.2.0]: ", "[0.0.9]: "
    )
    assert any("newest first" in p for p in problems(text))


def test_a_duplicate_version_is_rejected():
    text = VALID.replace("[0.1.0] - 2026-10-09", "[0.2.0] - 2026-10-09")
    assert any("0.2.0" in p and "more than once" in p for p in problems(text))


def test_an_unknown_category_is_rejected():
    text = VALID.replace("### Fixed", "### Bugfixes")
    assert any("Bugfixes" in p for p in problems(text))


def test_a_repeated_category_in_one_release_is_rejected():
    text = VALID.replace("### Fixed\n\n- A bug.", "### Added\n\n- A bug.")
    assert any("Added" in p and "more than once" in p for p in problems(text))


def test_an_entry_outside_a_category_is_rejected():
    text = VALID.replace(
        "## [0.2.0] - 2026-10-19\n\n", "## [0.2.0] - 2026-10-19\n\n- Loose.\n\n"
    )
    assert any("0.2.0" in p and "category" in p for p in problems(text))


def test_a_release_with_no_entries_is_rejected():
    text = VALID.replace("### Added\n\n- The first thing.\n\n", "")
    assert any("0.1.0" in p and "no entries" in p for p in problems(text))


def test_an_empty_category_is_rejected():
    text = VALID.replace("### Fixed\n\n- A bug.\n", "### Fixed\n")
    assert any("Fixed" in p and "empty" in p for p in problems(text))


def test_every_section_needs_a_link_reference():
    text = VALID.replace(f"[0.1.0]: {URL}/releases/tag/v0.1.0\n", "")
    assert any("0.1.0" in p and "link" in p for p in problems(text))


def test_a_link_reference_without_a_section_is_rejected():
    text = VALID + f"[0.0.5]: {URL}/releases/tag/v0.0.5\n"
    assert any("0.0.5" in p for p in problems(text))


def test_main_reports_problems_and_exits_non_zero(tmp_path, capsys):
    bad = tmp_path / "CHANGELOG.md"
    bad.write_text(VALID.replace("### Fixed", "### Bugfixes"))
    assert check_changelog.main(["check_changelog.py", str(bad)]) == 1
    assert "Bugfixes" in capsys.readouterr().err


def test_main_passes_a_valid_file(tmp_path):
    good = tmp_path / "CHANGELOG.md"
    good.write_text(VALID)
    assert check_changelog.main(["check_changelog.py", str(good)]) == 0
