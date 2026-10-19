#!/usr/bin/env python3
"""Fail if CHANGELOG.md does not follow Keep a Changelog 1.1.0.

Checked:

* The file starts with ``# Changelog``.
* The first section is ``## [Unreleased]``; every other section is
  ``## [X.Y.Z] - YYYY-MM-DD`` with a real date, each version once, newest first.
* Entries sit under ``### Added``, ``Changed``, ``Deprecated``, ``Removed``,
  ``Fixed`` or ``Security``, each at most once per section and never empty.
  A release has at least one entry; ``[Unreleased]`` may be empty.
* Every section has a link reference at the bottom, and every link reference
  has a section.

Usage: check_changelog.py [CHANGELOG ...]   (default CHANGELOG.md; as a prek hook)
"""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

CATEGORIES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
UNRELEASED = "Unreleased"
_SECTION = re.compile(r"^## \[(?P<name>[^\]]+)\](?P<rest>.*)$")
_RELEASE_REST = re.compile(r"^ - (?P<date>\d{4}-\d{2}-\d{2})$")
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_LINK = re.compile(r"^\[(?P<name>[^\]]+)\]: \S+$")


def validate(text: str) -> list[str]:
    problems: list[str] = []
    lines = text.splitlines()
    if not lines or lines[0] != "# Changelog":
        problems.append("the file must start with '# Changelog'")

    sections: list[str] = []
    links: list[str] = []
    versions: list[tuple[int, ...]] = []
    current: str | None = None
    categories: set[str] = set()
    category: str | None = None
    entries = 0
    category_entries = 0

    def close_category() -> None:
        if current is not None and category is not None and category_entries == 0:
            problems.append(f"[{current}]: '### {category}' is empty")

    def close_section() -> None:
        close_category()
        if current not in (None, UNRELEASED) and entries == 0:
            problems.append(f"[{current}] has no entries")

    for number, line in enumerate(lines, start=1):
        if link := _LINK.match(line):
            links.append(link["name"])
            continue
        if line.startswith("## "):
            close_section()
            match = _SECTION.match(line)
            if match is None:
                problems.append(
                    f"line {number}: section heading is not '## [name]': {line!r}"
                )
                current = None
                continue
            current, category, categories = match["name"], None, set()
            entries = category_entries = 0
            if current in sections:
                problems.append(f"[{current}] appears more than once")
            sections.append(current)
            if current == UNRELEASED:
                if len(sections) != 1:
                    problems.append("[Unreleased] must be the first section")
                if match["rest"]:
                    problems.append("[Unreleased] takes no date")
                continue
            if len(sections) == 1:
                problems.append("the first section must be [Unreleased]")
            version = _VERSION.match(current)
            if version is None:
                problems.append(f"[{current}] is not an X.Y.Z version")
            else:
                key = tuple(int(part) for part in version.groups())
                if versions and key >= versions[-1]:
                    problems.append(f"[{current}]: versions must be newest first")
                versions.append(key)
            rest = _RELEASE_REST.match(match["rest"])
            if rest is None:
                problems.append(f"[{current}] needs ' - YYYY-MM-DD' after the version")
            else:
                try:
                    datetime.date.fromisoformat(rest["date"])
                except ValueError:
                    problems.append(f"[{current}] has an invalid date {rest['date']}")
            continue
        if line.startswith("### "):
            close_category()
            name = line[4:].strip()
            if current is None:
                problems.append(f"line {number}: '### {name}' is outside a section")
            elif name not in CATEGORIES:
                problems.append(f"[{current}]: unknown category '### {name}'")
            elif name in categories:
                problems.append(f"[{current}]: '### {name}' appears more than once")
            categories.add(name)
            category, category_entries = name, 0
            continue
        if line.startswith("#") and number != 1:
            problems.append(f"line {number}: unexpected heading {line!r}")
            continue
        if line.startswith("- "):
            if current is None:
                continue  # an intro list before the first section
            if category is None:
                problems.append(
                    f"[{current}]: entry outside a category on line {number}"
                )
            entries += 1
            category_entries += 1
    close_section()

    for name in sections:
        if name not in links:
            problems.append(f"[{name}] has no link reference")
    for name in links:
        if name not in sections:
            problems.append(f"link reference [{name}] has no section")
    return problems


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv[1:]] or [Path("CHANGELOG.md")]
    failed = False
    for path in paths:
        for problem in validate(path.read_text()):
            print(f"{path}: {problem}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
