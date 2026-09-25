"""Validate a PR handoff before review, without model calls or source material."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

_SECTION = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_REQUIRED = ("Issue", "Scope", "Verification", "Review")
_SOURCE_GATED = ("source_map", "supabase/migrations/")
_DOC_PREFIXES = ("docs/", ".github/ISSUE_TEMPLATE/")


def validate(body: str, paths: list[str]) -> list[str]:
    """Return missing handoff fields; documentation-only PRs have a lighter gate."""
    matches = list(_SECTION.finditer(body))
    sections = {
        match.group(1): body[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(body)].strip()
        for index, match in enumerate(matches)
    }

    def filled(name: str) -> bool:
        value = sections.get(name, "")
        return bool(value and not re.fullmatch(r"<!--.*?-->", value, re.DOTALL))

    errors = [f"Missing or empty section: ## {name}" for name in _REQUIRED if not filled(name)]
    if filled("Issue") and not re.search(r"(?<!\w)#\d+\b", sections["Issue"]):
        errors.append("## Issue must reference a numbered GitHub issue")
    source_gated = any(
        marker in path.casefold() for path in paths for marker in _SOURCE_GATED
    )
    docs_only = bool(paths) and not source_gated and all(
        path.startswith(_DOC_PREFIXES) or path == ".github/PULL_REQUEST_TEMPLATE.md"
        for path in paths
    )
    if not docs_only and not filled("Risk and provenance"):
        errors.append("Code/schema/source changes require ## Risk and provenance")
    if source_gated and not filled("Gate evidence"):
        errors.append("Source Map or migration changes require ## Gate evidence")
    if not paths:
        errors.append("No changed files returned; cannot classify PR")
    return errors


def changed_paths(repository: str, number: int, token: str) -> list[str]:
    paths: list[str] = []
    for page in range(1, 32):
        url = (
            f"https://api.github.com/repos/{repository}/pulls/{number}/files"
            f"?per_page=100&page={page}"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            files = json.load(response)
        paths.extend(item["filename"] for item in files)
        if len(files) < 100:
            return paths
    raise RuntimeError("PR exceeds 3,000 files; inspect scope manually")


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr = event["pull_request"]
    errors = validate(
        pr.get("body") or "",
        changed_paths(os.environ["GITHUB_REPOSITORY"], pr["number"], os.environ["GH_TOKEN"]),
    )
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
