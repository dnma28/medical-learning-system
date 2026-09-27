#!/usr/bin/env python3
"""CLI wrapper for the deterministic GitHub work-item coordination guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_learning_system.work_item_guard import WorkItem, audit_all, validate_current


def _load(path: Path) -> list[WorkItem]:
    values = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(values, list):
        raise SystemExit("Issue snapshot must be a JSON list.")
    return [WorkItem.from_mapping(value) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issues", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--current-number", type=int)
    group.add_argument("--audit-all", action="store_true")
    args = parser.parse_args()

    items = _load(args.issues)
    errors = (
        audit_all(items)
        if args.audit_all
        else validate_current(items, args.current_number)
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("Work-item coordination guard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
