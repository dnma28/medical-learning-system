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
_REVIEW_STATUS = re.compile(r"(?im)^\s*Status:\s*(PASS|APPROVED)\s*$")
_REVIEW_PENDING = re.compile(r"(?im)^\s*Status:\s*PENDING\s*$")
_REVIEW_COMMIT = re.compile(r"(?im)^\s*Commit:\s*([0-9a-f]{40})\s*$")
_REVIEW_EVIDENCE = re.compile(
    r"(?im)^\s*Evidence:\s*https://github\.com/[^\s]+"
    r"(?:#issuecomment-\d+|#pullrequestreview-\d+)\s*$"
)


def validate(
    body: str,
    paths: list[str],
    head_sha: str | None = None,
    *,
    draft: bool = False,
) -> list[str]:
    """Return handoff/review gate errors; documentation-only PRs have a lighter risk gate."""
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
    if filled("Review"):
        review = sections["Review"]
        if draft:
            if not _REVIEW_PENDING.search(review):
                errors.append("Draft PRs must mark ## Review as 'Status: PENDING'")
        elif not _REVIEW_STATUS.search(review):
            errors.append("Ready PRs require ## Review 'Status: PASS' or 'Status: APPROVED'")
        if not draft:
            commit = _REVIEW_COMMIT.search(review)
            if commit is None:
                errors.append("## Review requires 'Commit: <40-char head SHA>'")
            elif head_sha is not None and commit.group(1) != head_sha:
                errors.append(
                    f"## Review is stale: reviewed {commit.group(1)}, current head is {head_sha}"
                )
        if not draft and not _REVIEW_EVIDENCE.search(review):
            errors.append("Ready PRs require a GitHub issue-comment or PR-review evidence URL")
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


def validate_independent_reviews(
    reviews: list[dict],
    pull_request_author: str,
    head_sha: str,
    *,
    body: str = "",
    repository: str = "",
    number: int = 0,
) -> list[str]:
    """Accept exact-HEAD non-author approval or an exact-HEAD model review artifact.

    A model session is process-separated, not GitHub-identity-separated. The
    coordinator must verify that the reviewer session actually ran independently.
    """
    latest_by_user: dict[str, dict] = {}
    for review in reviews:
        user = review.get("user") or {}
        login = user.get("login")
        if not login:
            continue
        previous = latest_by_user.get(login)
        if previous is None or (review.get("submitted_at") or "") >= (
            previous.get("submitted_at") or ""
        ):
            latest_by_user[login] = review

    matches = list(_SECTION.finditer(body))
    sections = {
        match.group(1): body[
            match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(body)
        ].strip()
        for index, match in enumerate(matches)
    }
    section = sections.get("Review", "")
    evidence = re.search(
        r"(?im)^Evidence:\s*https://github\.com/"
        + re.escape(repository)
        + r"/pull/" + str(number) + r"#pullrequestreview-(\d+)\s*$",
        section,
    ) if repository and number else None
    if not evidence:
        return ["Review evidence must link to a real review on this PR"]

    review_id = int(evidence.group(1))
    matched = [review for review in reviews if review.get("id") == review_id]
    if len(matched) != 1:
        return ["Model review evidence URL does not resolve to a PR review"]
    review = matched[0]
    user = review.get("user") or {}
    login = user.get("login")
    if (
        login and login != pull_request_author
        and user.get("type") != "Bot"
        and review.get("state") == "APPROVED"
        and review.get("commit_id") == head_sha
        and latest_by_user.get(login) is review
    ):
        return []

    mode = re.search(r"(?im)^Mode:\s*MODEL_INDEPENDENT\s*$", section)
    writer = re.search(r"(?im)^Writer-Session:\s*([A-Za-z0-9._:/-]{8,128})\s*$", section)
    if not (mode and writer):
        return ["Ready PR requires exact-HEAD non-author approval or a bound model review"]
    text = review.get("body") or ""

    def field(name: str) -> str | None:
        match = re.search(r"(?im)^" + re.escape(name) + r":[ \t]*([^\r\n]*?)[ \t]*$", text)
        return match.group(1).strip() if match else None

    reviewer_session = field("Reviewer-Session")
    checks = field("Evidence-Checks")
    summary = field("Summary")
    if (
        review.get("state") != "COMMENTED"
        or review.get("commit_id") != head_sha
        or field("Model-Review") != "PASS"
        or field("Reviewed-Commit") != head_sha
        or field("Writer-Session") != writer.group(1)
        or not reviewer_session
        or reviewer_session == writer.group(1)
        or not re.fullmatch(r"[A-Za-z0-9._:/-]{8,128}", reviewer_session)
        or not checks or len(checks) < 20
        or field("Unresolved-Blocking-Findings") != "0"
        or not summary or len(summary) < 30
    ):
        return ["Model review artifact lacks exact-HEAD PASS, distinct session, or evidence"]
    return []


def pull_request_reviews(repository: str, number: int, token: str) -> list[dict]:
    reviews: list[dict] = []
    for page in range(1, 32):
        url = (
            f"https://api.github.com/repos/{repository}/pulls/{number}/reviews"
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
            batch = json.load(response)
        reviews.extend(batch)
        if len(batch) < 100:
            return reviews
    raise RuntimeError("PR exceeds 3,100 reviews; inspect review history manually")


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr = event["pull_request"]
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    head_sha = pr["head"]["sha"]
    paths = changed_paths(repository, pr["number"], token)
    errors = validate(
        pr.get("body") or "",
        paths,
        head_sha,
        draft=bool(pr.get("draft")),
    )
    if not pr.get("draft"):
        reviews = pull_request_reviews(repository, pr["number"], token)
        errors.extend(
            validate_independent_reviews(
                reviews,
                (pr.get("user") or {}).get("login", ""),
                head_sha,
                body=pr.get("body") or "",
                repository=repository,
                number=pr["number"],
            )
        )
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
