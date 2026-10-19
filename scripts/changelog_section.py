#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md, for use as release notes.

The changelog follows Keep a Changelog: the section is everything under
``## [<version>] - <date>`` up to the next ``## `` heading or the link
references at the end of the file. Exits non-zero if the section is missing
or empty, so a release cannot go out without its changelog entry.

Usage: changelog_section.py VERSION [CHANGELOG]   (VERSION may start with "v")
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


_LINK = re.compile(r"^\[[^\]]+\]: \S+$")


class ChangelogError(Exception):
    """The changelog has no usable section for the requested version."""


def section(text: str, version: str) -> str:
    version = version.removeprefix("v")
    heading = re.compile(rf"^## \[{re.escape(version)}\] - \S+$")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if heading.match(line):
            body: list[str] = []
            for following in lines[i + 1 :]:
                if following.startswith("## ") or _LINK.match(following):
                    break
                body.append(following)
            notes = "\n".join(body).strip()
            if not notes:
                raise ChangelogError(f"the changelog section for {version} is empty")
            return notes + "\n"
    raise ChangelogError(f"the changelog has no section for {version}")


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    path = Path(argv[2]) if len(argv) == 3 else Path("CHANGELOG.md")
    try:
        sys.stdout.write(section(path.read_text(), argv[1]))
    except ChangelogError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
