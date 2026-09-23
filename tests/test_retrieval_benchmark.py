import math

import pytest

from medical_learning_system.retrieval.benchmark import (
    BenchmarkHit,
    BenchmarkQuery,
    BenchmarkRunRecord,
    score_query,
    summarize_run,
)


def query(
    query_id="q1",
    *,
    evidence=None,
    sources=None,
    structures=None,
):
    return BenchmarkQuery(
        query_id=query_id,
        query_text="abstract test query",
        relevant_evidence=evidence or {},
        relevant_sources=set(sources or []),
        relevant_structure_nodes=set(structures or []),
    )


def run(query_id="q1", hits=None, *, latency=10.0, cost=0.0):
    return BenchmarkRunRecord(
        query_id=query_id,
        retriever="test-retriever",
        k=3,
        latency_ms=latency,
        estimated_cost_usd=cost,
        hits=hits or [],
    )


def hit(evidence_id, source_id, structure_id=None, score=1.0):
    return BenchmarkHit(
        evidence_id=evidence_id,
        source_id=source_id,
        structure_node_id=structure_id,
        score=score,
    )


def test_query_requires_ground_truth():
    with pytest.raises(ValueError, match="ground truth"):
        query(evidence={}, sources=[], structures=[])


def test_summary_computes_recall_mrr_and_ndcg():
    q = query(
        evidence={"ev-a": 3, "ev-b": 1},
        sources=["src-a"],
        structures=["sec-a"],
    )
    r = run(
        hits=[
            hit("ev-x", "src-x", "sec-x"),
            hit("ev-a", "src-a", "sec-a"),
            hit("ev-b", "src-a", "sec-b"),
        ]
    )

    summary = summarize_run([q], [r])

    assert summary.evidence_recall_at_k == 1.0
    assert summary.evidence_mrr_at_k == 0.5
    assert summary.source_recall_at_k == 1.0
    assert summary.source_mrr_at_k == 0.5
    assert summary.structure_recall_at_k == 1.0
    assert summary.structure_mrr_at_k == 0.5
    assert summary.evidence_ndcg_at_k is not None
    assert 0.0 < summary.evidence_ndcg_at_k < 1.0


def test_metrics_ignore_dimensions_without_gold_labels():
    q = query(sources=["src-a"])
    r = run(hits=[hit("ev-a", "src-a")])

    summary = summarize_run([q], [r])

    assert summary.evidence_recall_at_k is None
    assert summary.evidence_mrr_at_k is None
    assert summary.evidence_ndcg_at_k is None
    assert summary.source_recall_at_k == 1.0
    assert summary.structure_recall_at_k is None


def test_summary_separates_quality_latency_and_cost():
    queries = [
        query("q1", sources=["src-a"]),
        query("q2", sources=["src-b"]),
    ]
    runs = [
        run("q1", [hit("ev-a", "src-a")], latency=10.0, cost=0.01),
        run("q2", [hit("ev-x", "src-x")], latency=30.0, cost=0.02),
    ]

    summary = summarize_run(queries, runs)

    assert summary.source_recall_at_k == 0.5
    assert summary.mean_latency_ms == 20.0
    assert summary.p95_latency_ms == 30.0
    assert math.isclose(summary.total_estimated_cost_usd, 0.03)


def test_summary_rejects_mixed_retrievers():
    q = query(sources=["src-a"])
    first = run(hits=[hit("ev-a", "src-a")])
    second = first.model_copy(update={"retriever": "other"})

    with pytest.raises(ValueError, match="one retriever"):
        summarize_run([q], [first, second])


def test_graded_relevance_rewards_better_ordering():
    q = query(evidence={"high": 3, "low": 1})

    better = summarize_run(
        [q],
        [run(hits=[hit("high", "s"), hit("low", "s")])],
    )
    worse = summarize_run(
        [q],
        [run(hits=[hit("low", "s"), hit("high", "s")])],
    )

    assert better.evidence_ndcg_at_k == 1.0
    assert worse.evidence_ndcg_at_k < better.evidence_ndcg_at_k


def test_structure_mrr_treats_multiple_nodes_on_one_hit_as_same_rank():
    q = query(structures=["target-section"])
    r = run(
        hits=[
            BenchmarkHit(
                evidence_id="ev-a",
                source_id="src-a",
                structure_node_ids={"chapter", "target-section", "candidate-other"},
                score=1.0,
            ),
            hit("ev-b", "src-b", "later-section"),
        ]
    )

    summary = summarize_run([q], [r])

    assert summary.structure_recall_at_k == 1.0
    assert summary.structure_mrr_at_k == 1.0

