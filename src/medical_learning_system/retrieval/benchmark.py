from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Iterable
from typing import Protocol
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class BenchmarkQuery(BaseModel):
    query_id: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    language: str | None = None
    relevant_evidence: dict[str, int] = Field(default_factory=dict)
    relevant_sources: set[str] = Field(default_factory=set)
    relevant_structure_nodes: set[str] = Field(default_factory=set)
    tags: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def has_ground_truth(self) -> "BenchmarkQuery":
        if not (
            self.relevant_evidence
            or self.relevant_sources
            or self.relevant_structure_nodes
        ):
            raise ValueError("benchmark query needs source-backed ground truth")
        if any(grade <= 0 for grade in self.relevant_evidence.values()):
            raise ValueError("evidence relevance grades must be positive")
        return self


class BenchmarkHit(BaseModel):
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    structure_node_id: str | None = None
    score: float


class RetrievalResponse(BaseModel):
    hits: list[BenchmarkHit]
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)


class Retriever(Protocol):
    name: str

    def retrieve(self, query: str, k: int) -> RetrievalResponse: ...


class BenchmarkRunRecord(BaseModel):
    query_id: str
    retriever: str
    k: int = Field(gt=0)
    latency_ms: float = Field(ge=0.0)
    estimated_cost_usd: float = Field(ge=0.0)
    hits: list[BenchmarkHit]


class QueryMetrics(BaseModel):
    query_id: str
    evidence_recall_at_k: float | None = None
    evidence_mrr_at_k: float | None = None
    evidence_ndcg_at_k: float | None = None
    source_recall_at_k: float | None = None
    source_mrr_at_k: float | None = None
    structure_recall_at_k: float | None = None
    structure_mrr_at_k: float | None = None


class BenchmarkSummary(BaseModel):
    retriever: str
    queries: int
    k: int
    evidence_recall_at_k: float | None = None
    evidence_mrr_at_k: float | None = None
    evidence_ndcg_at_k: float | None = None
    source_recall_at_k: float | None = None
    source_mrr_at_k: float | None = None
    structure_recall_at_k: float | None = None
    structure_mrr_at_k: float | None = None
    mean_latency_ms: float
    p95_latency_ms: float
    total_estimated_cost_usd: float


def run_benchmark(
    queries: Iterable[BenchmarkQuery],
    retriever: Retriever,
    *,
    k: int = 10,
) -> list[BenchmarkRunRecord]:
    if k < 1:
        raise ValueError("k must be >= 1")

    records: list[BenchmarkRunRecord] = []
    for query in queries:
        started = time.perf_counter()
        response = retriever.retrieve(query.query_text, k)
        latency_ms = (time.perf_counter() - started) * 1000.0
        records.append(
            BenchmarkRunRecord(
                query_id=query.query_id,
                retriever=retriever.name,
                k=k,
                latency_ms=latency_ms,
                estimated_cost_usd=response.estimated_cost_usd,
                hits=response.hits[:k],
            )
        )
    return records


def score_query(
    query: BenchmarkQuery,
    run: BenchmarkRunRecord,
) -> QueryMetrics:
    hits = run.hits[: run.k]

    evidence_ids = [hit.evidence_id for hit in hits]
    source_ids = [hit.source_id for hit in hits]
    structure_ids = [
        hit.structure_node_id for hit in hits if hit.structure_node_id is not None
    ]

    evidence_relevant = set(query.relevant_evidence)
    return QueryMetrics(
        query_id=query.query_id,
        evidence_recall_at_k=_recall(evidence_ids, evidence_relevant),
        evidence_mrr_at_k=_mrr(evidence_ids, evidence_relevant),
        evidence_ndcg_at_k=_ndcg(
            evidence_ids,
            query.relevant_evidence,
            run.k,
        )
        if evidence_relevant
        else None,
        source_recall_at_k=_recall(source_ids, query.relevant_sources),
        source_mrr_at_k=_mrr(source_ids, query.relevant_sources),
        structure_recall_at_k=_recall(
            structure_ids, query.relevant_structure_nodes
        ),
        structure_mrr_at_k=_mrr(
            structure_ids, query.relevant_structure_nodes
        ),
    )


def summarize_run(
    queries: Iterable[BenchmarkQuery],
    runs: Iterable[BenchmarkRunRecord],
) -> BenchmarkSummary:
    query_map = {query.query_id: query for query in queries}
    run_list = list(runs)
    if not run_list:
        raise ValueError("benchmark run is empty")

    retrievers = {run.retriever for run in run_list}
    ks = {run.k for run in run_list}
    if len(retrievers) != 1 or len(ks) != 1:
        raise ValueError("summary requires one retriever and one k")

    metrics: list[QueryMetrics] = []
    for run in run_list:
        query = query_map.get(run.query_id)
        if query is None:
            raise KeyError(f"missing benchmark query: {run.query_id}")
        metrics.append(score_query(query, run))

    latencies = [run.latency_ms for run in run_list]
    return BenchmarkSummary(
        retriever=run_list[0].retriever,
        queries=len(run_list),
        k=run_list[0].k,
        evidence_recall_at_k=_mean_optional(
            metric.evidence_recall_at_k for metric in metrics
        ),
        evidence_mrr_at_k=_mean_optional(
            metric.evidence_mrr_at_k for metric in metrics
        ),
        evidence_ndcg_at_k=_mean_optional(
            metric.evidence_ndcg_at_k for metric in metrics
        ),
        source_recall_at_k=_mean_optional(
            metric.source_recall_at_k for metric in metrics
        ),
        source_mrr_at_k=_mean_optional(
            metric.source_mrr_at_k for metric in metrics
        ),
        structure_recall_at_k=_mean_optional(
            metric.structure_recall_at_k for metric in metrics
        ),
        structure_mrr_at_k=_mean_optional(
            metric.structure_mrr_at_k for metric in metrics
        ),
        mean_latency_ms=statistics.fmean(latencies),
        p95_latency_ms=_percentile(latencies, 0.95),
        total_estimated_cost_usd=sum(
            run.estimated_cost_usd for run in run_list
        ),
    )


def load_queries_jsonl(path: Path) -> list[BenchmarkQuery]:
    return [
        BenchmarkQuery.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_runs_jsonl(path: Path) -> list[BenchmarkRunRecord]:
    return [
        BenchmarkRunRecord.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_runs_jsonl(path: Path, runs: Iterable[BenchmarkRunRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [run.model_dump_json() for run in runs]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _recall(ranked: list[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    return len(set(ranked) & relevant) / len(relevant)


def _mrr(ranked: list[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    for rank, value in enumerate(ranked, start=1):
        if value in relevant:
            return 1.0 / rank
    return 0.0


def _ndcg(
    ranked: list[str],
    relevance: dict[str, int],
    k: int,
) -> float:
    gains = [relevance.get(value, 0) for value in ranked[:k]]
    dcg = _dcg(gains)
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = _dcg(ideal)
    return dcg / idcg if idcg > 0 else 0.0


def _dcg(grades: list[int]) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(grades, start=1)
    )


def _mean_optional(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return statistics.fmean(usable) if usable else None


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]
