from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_learning_system.coverage import CoverageStore
from medical_learning_system.evidence_alignment import EvidenceLinkStore
from medical_learning_system.evidence_store import EvidenceStore
from medical_learning_system.retrieval.benchmark import write_runs_jsonl
from medical_learning_system.retrieval.benchmark_gold import load_source_gold_jsonl
from medical_learning_system.retrieval.embedding_providers import (
    SentenceTransformerProvider,
)
from medical_learning_system.retrieval.evaluation_gate import (
    KeywordBaselineRetriever,
    SemanticCorpusRetriever,
    build_grounded_corpus,
    evaluate_retrievers,
    resolve_gold_strict,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate real source-grounded retrieval from a private pilot SQLite DB. "
            "No source text is written to the report."
        )
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--logical-source-id", required=True)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--semantic-model")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/local/evaluation"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    coverage = CoverageStore(args.db)
    evidence_store = EvidenceStore(args.db)
    link_store = EvidenceLinkStore(args.db)

    nodes = coverage.get_structure(args.source_id)
    evidence = evidence_store.list_source(args.source_id)
    items = load_source_gold_jsonl(args.gold)
    queries = resolve_gold_strict(
        items,
        logical_source_id=args.logical_source_id,
        physical_source_id=args.source_id,
        nodes=nodes,
        link_store=link_store,
    )

    corpus = build_grounded_corpus(evidence, link_store)
    retrievers = [KeywordBaselineRetriever(corpus)]
    if args.semantic_model:
        provider = SentenceTransformerProvider(args.semantic_model)
        retrievers.append(SemanticCorpusRetriever(corpus, provider))

    report, runs = evaluate_retrievers(
        source_id=args.source_id,
        logical_source_id=args.logical_source_id,
        queries=queries,
        evidence=evidence,
        link_store=link_store,
        retrievers=retrievers,
        k=args.k,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "report.json"
    report_path.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    for name, records in runs.items():
        safe_name = "".join(
            char if char.isalnum() or char in "-_." else "_"
            for char in name
        )
        write_runs_jsonl(args.output_dir / f"{safe_name}.jsonl", records)

    print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
