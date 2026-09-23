from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from medical_learning_system.coverage import CoverageStore
from medical_learning_system.evidence_store import EvidenceStore
from medical_learning_system.evidence_alignment import (
    AlignmentMethod,
    EvidenceLinkStore,
    align_evidence_to_structure,
)
from medical_learning_system.native_pdf_text import (
    native_pdf_page_count,
    parsed_document_from_native_pdf,
)
from medical_learning_system.parser_contract import materialize_evidence_only
from medical_learning_system.pdf_outline import structure_from_pdf_outline
from medical_learning_system.retrieval.benchmark_gold import (
    load_source_gold_jsonl,
    resolve_source_gold,
)
from medical_learning_system.source_registry import (
    SourceKind,
    SourceRecord,
    SourceRegistry,
    SourceStatus,
)
from medical_learning_system.sources import sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the low-cost native-PDF pilot ingestion pipeline."
    )
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--logical-source-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/local/pilot.sqlite3"),
    )
    parser.add_argument("--gold", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = args.file.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    digest = sha256_file(path)
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    registry = SourceRegistry(args.db)
    coverage = CoverageStore(args.db)
    evidence = EvidenceStore(args.db)
    links = EvidenceLinkStore(args.db)

    source = SourceRecord(
        source_id=args.source_id,
        logical_source_id=args.logical_source_id,
        provider="local",
        provider_file_id=args.source_id,
        title=args.title,
        mime_type="application/pdf",
        size_bytes=path.stat().st_size,
        modified_time=modified,
        kind=SourceKind.TEXTBOOK,
    )
    registry.upsert(source)

    structure = structure_from_pdf_outline(
        args.source_id,
        args.title,
        path,
    )
    parsed = parsed_document_from_native_pdf(path)
    blocks = materialize_evidence_only(
        source_id=args.source_id,
        parsed=parsed,
    )

    coverage.replace_structure(args.source_id, structure.nodes)
    evidence.replace_source(args.source_id, blocks)
    aligned = align_evidence_to_structure(structure.nodes, blocks)
    links.replace_source(args.source_id, aligned)
    registry.set_status(
        args.source_id,
        SourceStatus.PARSED,
        content_sha256=digest,
    )

    result = {
        "source_id": args.source_id,
        "pdf_pages": native_pdf_page_count(path),
        "structure_nodes": len(structure.nodes),
        "evidence_blocks": len(blocks),
        "evidence_structure_links": len(aligned),
        "alignment_exact": sum(
            link.method == AlignmentMethod.EXACT_HEADING for link in aligned
        ),
        "alignment_sequence": sum(
            link.method == AlignmentMethod.HEADING_SEQUENCE for link in aligned
        ),
        "alignment_candidates": sum(
            link.method == AlignmentMethod.PAGE_RANGE_CANDIDATE for link in aligned
        ),
        "content_sha256": digest,
    }

    if args.gold:
        gold = load_source_gold_jsonl(args.gold)
        resolved = resolve_source_gold(
            gold,
            logical_source_id=args.logical_source_id,
            physical_source_id=args.source_id,
            nodes=structure.nodes,
        )
        result["gold_queries_resolved"] = len(resolved)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
