from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from medical_learning_system.compiler import (
    CompilationError,
    build_native_pdf_compiler,
)
from medical_learning_system.source_registry import SourceKind, SourceRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally compile one private PDF into reusable source data."
    )
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=Path("data/local/library.sqlite3"))
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--logical-source-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--domain")
    parser.add_argument("--edition")
    parser.add_argument("--publication-year", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = args.file.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    source = SourceRecord(
        source_id=args.source_id,
        logical_source_id=args.logical_source_id,
        provider="local",
        provider_file_id=args.source_id,
        title=args.title,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        modified_time=datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=timezone.utc,
        ),
        kind=SourceKind.TEXTBOOK,
        domain=args.domain,
        edition=args.edition,
        publication_year=args.publication_year,
    )

    compiler = build_native_pdf_compiler(args.db)
    try:
        outcome = compiler.compile(source, path)
    except CompilationError as exc:
        print(json.dumps(exc.manifest.model_dump(mode="json"), indent=2))
        raise

    print(
        json.dumps(
            {
                "action": outcome.action.value,
                "manifest": outcome.manifest.model_dump(mode="json"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
