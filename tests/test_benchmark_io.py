from medical_learning_system.retrieval.benchmark import (
    BenchmarkHit,
    BenchmarkQuery,
    BenchmarkRunRecord,
    load_queries_jsonl,
    load_runs_jsonl,
    write_runs_jsonl,
)


def test_jsonl_round_trip(tmp_path):
    query_file = tmp_path / "queries.jsonl"
    query_file.write_text(
        BenchmarkQuery(
            query_id="q1",
            query_text="abstract query",
            relevant_sources={"source-1"},
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )

    run_file = tmp_path / "runs.jsonl"
    records = [
        BenchmarkRunRecord(
            query_id="q1",
            retriever="baseline",
            k=5,
            latency_ms=1.0,
            estimated_cost_usd=0.0,
            hits=[
                BenchmarkHit(
                    evidence_id="ev-1",
                    source_id="source-1",
                    score=1.0,
                )
            ],
        )
    ]
    write_runs_jsonl(run_file, records)

    assert load_queries_jsonl(query_file)[0].query_id == "q1"
    assert load_runs_jsonl(run_file)[0].hits[0].evidence_id == "ev-1"
