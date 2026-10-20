#!/usr/bin/env python3
"""Scan files Git would publish for common secrets and private identifiers."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "private-ipv4": re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "uuid": re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
        r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
    ),
    "home-path": re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+"),
    "credential-assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|token|encryption[_-]?key|"
        r"private[_-]?key)\b\s*[:=]\s*[\"']?([^\s\"']+)"
    ),
    "telegram-api-hash": re.compile(r"\b[0-9a-fA-F]{32}\b"),
    "international-phone": re.compile(r"(?<!\w)\+[1-9][0-9]{9,14}(?!\w)"),
}

SAFE_MARKERS = (
    "example.invalid",
    "change-me",
    "placeholder",
    "getpass.getpass",
    "password=password",
    "${",
)


def git_publishable_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--forbid", action="append", default=[])
    args = parser.parse_args()
    root = args.root.resolve()

    findings: list[str] = []
    for path in git_publishable_files(root):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-utf8: {path.relative_to(root)}")
            continue

        for line_number, line in enumerate(text.splitlines(), 1):
            for literal in args.forbid:
                if literal and literal.casefold() in line.casefold():
                    findings.append(
                        f"forbidden-literal: {path.relative_to(root)}:{line_number}"
                    )
            for label, pattern in PATTERNS.items():
                for match in pattern.finditer(line):
                    if any(marker in line for marker in SAFE_MARKERS):
                        continue
                    findings.append(
                        f"{label}: {path.relative_to(root)}:{line_number}: {match.group(0)}"
                    )

    if findings:
        print("\n".join(findings))
        return 1
    print("PASS: no common secrets or private identifiers detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
