from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_learning_system.knowledge_graph.v5_migration import (
    audit_v5_corpus,
    migrate_v5_patch_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit exported KG v5 patch text without modifying canonical data."
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    migrations = [
        migrate_v5_patch_text(path.name, path.read_text(encoding="utf-8"))
        for path in args.files
    ]
    report = audit_v5_corpus(migrations)
    rendered = json.dumps(
        report.model_dump(mode="json"),
        indent=2,
        ensure_ascii=False,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
