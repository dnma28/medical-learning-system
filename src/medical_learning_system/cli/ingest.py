from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from medical_learning_system.retrieval.openai_provider import build_openai_rag
from medical_learning_system.retrieval.rag_anything_adapter import RAGConfig
from medical_learning_system.sources import load_manifest, sha256_file


SUPPORTED_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".md"
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest one local source into the Medical Learning System RAG index."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--working-dir", type=Path, default=Path("./rag_storage"))
    parser.add_argument("--output-dir", type=Path, default=Path("./output"))
    parser.add_argument(
        "--parser",
        choices=["mineru", "docling", "paddleocr"],
        default="mineru",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    load_dotenv()
    manifest = load_manifest(args.manifest)
    source_file = args.file.expanduser().resolve()

    if not source_file.exists():
        raise FileNotFoundError(source_file)
    if source_file.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported source type: {source_file.suffix}")

    file_hash = sha256_file(source_file)

    config = RAGConfig(
        working_dir=args.working_dir,
        parser=args.parser,
        parse_method="auto",
    )
    rag = build_openai_rag(config)

    source_output = args.output_dir / manifest.source_id
    source_output.mkdir(parents=True, exist_ok=True)

    await rag.process_document_complete(
        file_path=str(source_file),
        output_dir=str(source_output),
        parse_method="auto",
    )

    local_record_dir = Path("./data/local/ingestion")
    local_record_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "source_id": manifest.source_id,
        "title": manifest.title,
        "edition": manifest.edition,
        "publication_year": manifest.publication_year,
        "file_name": source_file.name,
        "sha256": file_hash,
        "parser": args.parser,
        "working_dir": str(args.working_dir),
        "output_dir": str(source_output),
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    record_path = local_record_dir / f"{manifest.source_id}.json"
    record_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Ingested: {manifest.title}")
    print(f"Source ID: {manifest.source_id}")
    print(f"SHA256: {file_hash}")
    print(f"Local record: {record_path}")


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
