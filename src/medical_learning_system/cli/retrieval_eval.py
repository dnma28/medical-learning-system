from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from medical_learning_system.coverage import CoverageStore
from medical_learning_system.evidence_alignment import EvidenceLinkStore
from medical_learning_system.evidence_store import EvidenceStore
from medical_learning_system.retrieval.benchmark import (
    run_benchmark,
    summarize_run,
    write_runs_jsonl,
)
from medical_learning_system.retrieval.benchmark_gold import (
    load_source_gold_jsonl,
    resolve_source_gold,
)
from medical_learning_system.retrieval.embedding_providers import (
    SentenceTransformerProvider,
)
from medical_learning_system.retrieval.local_retrievers import (
    LocalKeywordRetriever,
    LocalSemanticRetriever,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run source-grounded retrieval evaluation on local pilot data."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--logical-source-id", required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument(
        "--mode",
        choices=("keyword", "semantic"),
        default="keyword",
    )
    parser.add_argument("--embedding-model")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.k < 1:
        raise ValueError("--k must be >= 1")

    coverage = CoverageStore(args.db)
    evidence = EvidenceStore(args.db)
    links = EvidenceLinkStore(args.db)

    nodes = coverage.get_structure(args.source_id)
    gold = load_source_gold_jsonl(args.gold)
    queries = resolve_source_gold(
        gold,
        logical_source_id=args.logical_source_id,
        physical_source_id=args.source_id,
        nodes=nodes,
    )

    if args.mode == "keyword":
        retriever = LocalKeywordRetriever(evidence, links, args.source_id)
    else:
        if not args.embedding_model:
            raise ValueError("--embedding-model is required for semantic mode")
        provider = SentenceTransformerProvider(args.embedding_model)
        retriever = LocalSemanticRetriever(
            evidence,
            links,
            args.source_id,
            provider,
        )

    runs = run_benchmark(queries, retriever, k=args.k)
    summary = summarize_run(queries, runs)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_runs_jsonl(args.out_dir / f"{args.mode}_runs.jsonl", runs)

    evidence_blocks = evidence.list_source(args.source_id)
    linked_evidence_blocks = 0
    method_counts: Counter[str] = Counter()
    for block in evidence_blocks:
        block_links = links.list_evidence(block.evidence_id)
        if block_links:
            linked_evidence_blocks += 1
        method_counts.update(link.method.value for link in block_links)

    report = {
        "source_id": args.source_id,
        "logical_source_id": args.logical_source_id,
        "mode": args.mode,
        "retriever": retriever.name,
        "k": args.k,
        "gold_queries": len(queries),
        "evidence_blocks": len(evidence_blocks),
        "linked_evidence_blocks": linked_evidence_blocks,
        "alignment_link_methods": dict(method_counts),
        "summary": summary.model_dump(),
    }
    (args.out_dir / f"{args.mode}_summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
