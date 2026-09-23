from __future__ import annotations

import argparse
import json
from pathlib import Path

from medical_learning_system.retrieval.benchmark import (
    load_queries_jsonl,
    load_runs_jsonl,
    summarize_run,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a saved retrieval benchmark run without API calls."
    )
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = summarize_run(
        load_queries_jsonl(args.queries),
        load_runs_jsonl(args.runs),
    )
    print(json.dumps(summary.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
