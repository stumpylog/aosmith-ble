#!/usr/bin/env python3
"""Fail if a file contains a device-identifying value that must not be published.

Two layers:

* Built-in shape checks: any MAC address other than the AA:BB:CC:DD:EE:FF
  placeholder, and any Salesforce-style 18-character assetID other than the
  02iQk000000EXAMPLE placeholder.
* An optional private pattern file (one case-insensitive regex per line) holding
  the exact real values. It is never committed. Path: $AOSMITH_REDACT_PATTERNS,
  else ~/.config/aosmith-ble/redact-patterns.txt. If it is missing, only the
  built-in checks run.

Usage: check_identifiers.py FILE [FILE ...]   (as a prek/pre-commit hook)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
ASSET_RE = re.compile(r"\b02iQk[0-9A-Za-z]{13}\b")
ALLOWED_MAC = "AA:BB:CC:DD:EE:FF"
ALLOWED_ASSET = "02iQk000000EXAMPLE"


def load_private_patterns() -> list[re.Pattern[str]]:
    path = Path(
        os.environ.get(
            "AOSMITH_REDACT_PATTERNS",
            Path.home() / ".config" / "aosmith-ble" / "redact-patterns.txt",
        ),
    )
    if not path.is_file():
        return []
    lines = (ln.strip() for ln in path.read_text().splitlines())
    return [
        re.compile(re.escape(ln), re.IGNORECASE)
        for ln in lines
        if ln and not ln.startswith("#")
    ]


def scan(path: Path, private: list[re.Pattern[str]]) -> list[str]:
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return []
    problems: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in MAC_RE.finditer(line):
            if m.group(0).upper() != ALLOWED_MAC:
                problems.append(f"{path}:{lineno}: MAC address {m.group(0)}")
        for m in ASSET_RE.finditer(line):
            if m.group(0) != ALLOWED_ASSET:
                problems.append(f"{path}:{lineno}: assetID-shaped value {m.group(0)}")
        for pat in private:
            if pat.search(line):
                problems.append(f"{path}:{lineno}: matches a private redaction pattern")
    return problems


def main(argv: list[str]) -> int:
    private = load_private_patterns()
    problems = [p for name in argv[1:] for p in scan(Path(name), private)]
    for p in problems:
        print(p)
    if problems:
        print(
            f"\n{len(problems)} identifier problem(s). Replace with the documented placeholders."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
