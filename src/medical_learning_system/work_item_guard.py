"""Deterministic coordination guard for GitHub AI work items."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_WORK_KEY_RE = re.compile(
    r"(?im)^\s*Work key:\s*`?([a-z0-9][a-z0-9:._/-]{2,127})`?\s*$"
)
_MANAGED_MARKERS = ("## Parent and outcome", "## Claim and handoff")


@dataclass(frozen=True)
class WorkItem:
    number: int
    title: str
    body: str
    url: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "WorkItem":
        return cls(
            number=int(value["number"]),
            title=str(value.get("title") or ""),
            body=str(value.get("body") or ""),
            url=str(value.get("url") or ""),
        )


def is_managed_work_item(body: str | None) -> bool:
    text = body or ""
    return all(marker in text for marker in _MANAGED_MARKERS)


def extract_work_key(body: str | None) -> str | None:
    match = _WORK_KEY_RE.search(body or "")
    return match.group(1).lower() if match else None


def duplicate_work_keys(items: Iterable[WorkItem]) -> dict[str, tuple[WorkItem, ...]]:
    grouped: dict[str, list[WorkItem]] = defaultdict(list)
    for item in items:
        key = extract_work_key(item.body)
        if key:
            grouped[key].append(item)
    return {
        key: tuple(sorted(group, key=lambda item: item.number))
        for key, group in grouped.items()
        if len(group) > 1
    }


def validate_current(items: Iterable[WorkItem], current_number: int) -> list[str]:
    item_list = list(items)
    current = next((item for item in item_list if item.number == current_number), None)
    if current is None:
        return [f"Current issue #{current_number} is not present in the open-issue snapshot."]

    if is_managed_work_item(current.body) and not extract_work_key(current.body):
        return [
            f"Issue #{current.number} is an AI work item but has no valid 'Work key:' line."
        ]

    key = extract_work_key(current.body)
    if not key:
        return []

    siblings = [
        item for item in item_list
        if item.number != current.number and extract_work_key(item.body) == key
    ]
    if not siblings:
        return []

    refs = ", ".join(
        f"#{item.number}" + (f" ({item.url})" if item.url else "")
        for item in sorted(siblings, key=lambda item: item.number)
    )
    return [
        f"Duplicate Work key '{key}' for issue #{current.number}; existing open issue(s): {refs}."
    ]


def audit_all(items: Iterable[WorkItem]) -> list[str]:
    item_list = list(items)
    errors: list[str] = []
    for key, group in sorted(duplicate_work_keys(item_list).items()):
        refs = ", ".join(f"#{item.number}" for item in group)
        errors.append(f"Duplicate Work key '{key}': {refs}.")
    return errors
