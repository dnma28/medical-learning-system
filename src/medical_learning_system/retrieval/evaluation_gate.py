from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from ..coverage import StructureNode
from ..evidence_alignment import AlignmentMethod, EvidenceLinkStore
from ..evidence_store import SourceEvidenceBlock
from .benchmark import (
    BenchmarkHit,
    BenchmarkQuery,
    BenchmarkRunRecord,
    BenchmarkSummary,
    RetrievalResponse,
    Retriever,
    run_benchmark,
    summarize_run,
)
from .benchmark_gold import (
    GoldResolutionError,
    SourceGroundedBenchmarkItem,
    resolve_source_gold,
)
from .embedding_providers import EmbeddingProvider


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class EvaluationGateError(RuntimeError):
    pass


class GroundedEvidence(BaseModel):
    evidence_id: str
    source_id: str
    text: str = Field(min_length=1)
    structure_node_ids: set[str]


class AlignmentCoverage(BaseModel):
    total_evidence: int
    text_evidence: int
    grounded_text_evidence: int
    ungrounded_text_evidence: int
    grounded_fraction: float
    exact_evidence: int
    prefix_evidence: int
    sequence_evidence: int
    candidate_only_evidence: int


class RetrievalEvaluationReport(BaseModel):
    source_id: str
    logical_source_id: str
    queries: int
    languages: dict[str, int]
    alignment: AlignmentCoverage
    no_hit_queries: dict[str, int]
    summaries: list[BenchmarkSummary]


def build_grounded_corpus(
    evidence: Sequence[SourceEvidenceBlock],
    link_store: EvidenceLinkStore,
) -> list[GroundedEvidence]:
    """Index only text evidence with explicit source-structure links."""
    corpus: list[GroundedEvidence] = []
    for block in evidence:
        if not block.text or not block.text.strip():
            continue
        links = link_store.list_evidence(block.evidence_id)
        node_ids = {link.node_id for link in links}
        if not node_ids:
            continue
        corpus.append(
            GroundedEvidence(
                evidence_id=block.evidence_id,
                source_id=block.source_id,
                text=block.text,
                structure_node_ids=node_ids,
            )
        )
    return corpus


def alignment_coverage(
    evidence: Sequence[SourceEvidenceBlock],
    link_store: EvidenceLinkStore,
) -> AlignmentCoverage:
    text_blocks = [block for block in evidence if block.text and block.text.strip()]
    method_ids: dict[AlignmentMethod, set[str]] = {
        method: set() for method in AlignmentMethod
    }
    grounded: set[str] = set()

    for block in text_blocks:
        links = link_store.list_evidence(block.evidence_id)
        if links:
            grounded.add(block.evidence_id)
        for link in links:
            method_ids[link.method].add(block.evidence_id)

    candidate_only = {
        block.evidence_id
        for block in text_blocks
        if block.evidence_id in method_ids[AlignmentMethod.PAGE_RANGE_CANDIDATE]
        and block.evidence_id not in method_ids[AlignmentMethod.EXACT_HEADING]
        and block.evidence_id not in method_ids[AlignmentMethod.HEADING_PREFIX]
        and block.evidence_id not in method_ids[AlignmentMethod.HEADING_SEQUENCE]
    }

    total_text = len(text_blocks)
    return AlignmentCoverage(
        total_evidence=len(evidence),
        text_evidence=total_text,
        grounded_text_evidence=len(grounded),
        ungrounded_text_evidence=total_text - len(grounded),
        grounded_fraction=(len(grounded) / total_text) if total_text else 0.0,
        exact_evidence=len(method_ids[AlignmentMethod.EXACT_HEADING]),
        prefix_evidence=len(method_ids[AlignmentMethod.HEADING_PREFIX]),
        sequence_evidence=len(method_ids[AlignmentMethod.HEADING_SEQUENCE]),
        candidate_only_evidence=len(candidate_only),
    )


def resolve_gold_strict(
    items: list[SourceGroundedBenchmarkItem],
    *,
    logical_source_id: str,
    physical_source_id: str,
    nodes: list[StructureNode],
    link_store: EvidenceLinkStore,
) -> list[BenchmarkQuery]:
    """Resolve heading anchors and require evidence for every target node."""
    try:
        queries = resolve_source_gold(
            items,
            logical_source_id=logical_source_id,
            physical_source_id=physical_source_id,
            nodes=nodes,
        )
    except GoldResolutionError as exc:
        raise EvaluationGateError(str(exc)) from exc

    missing: list[str] = []
    for query in queries:
        for node_id in sorted(query.relevant_structure_nodes):
            if not link_store.list_node(physical_source_id, node_id):
                missing.append(f"{query.query_id}:{node_id}")

    if missing:
        joined = ", ".join(missing)
        raise EvaluationGateError(
            "gold targets have no grounded evidence links: " + joined
        )
    return queries


class KeywordBaselineRetriever:
    """Deterministic local token-overlap baseline with no model/API cost."""

    name = "keyword-token-overlap"

    def __init__(self, corpus: Sequence[GroundedEvidence]):
        self._corpus = list(corpus)
        self._tokens = [Counter(_tokens(item.text)) for item in self._corpus]

    def retrieve(self, query: str, k: int) -> RetrievalResponse:
        query_tokens = Counter(_tokens(query))
        scored: list[tuple[float, GroundedEvidence]] = []
        for item, document_tokens in zip(self._corpus, self._tokens):
            overlap = sum(
                min(count, document_tokens.get(token, 0))
                for token, count in query_tokens.items()
            )
            if overlap <= 0:
                continue

            denominator = math.sqrt(
                max(sum(query_tokens.values()), 1)
                * max(sum(document_tokens.values()), 1)
            )
            score = overlap / denominator if denominator else 0.0
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda pair: (-pair[0], pair[1].evidence_id))
        return RetrievalResponse(
            hits=[
                BenchmarkHit(
                    evidence_id=item.evidence_id,
                    source_id=item.source_id,
                    structure_node_ids=item.structure_node_ids,
                    score=score,
                )
                for score, item in scored[:k]
            ],
            estimated_cost_usd=0.0,
        )


class SemanticCorpusRetriever:
    """Provider-neutral cosine retrieval for a small benchmark corpus."""

    def __init__(
        self,
        corpus: Sequence[GroundedEvidence],
        provider: EmbeddingProvider,
    ):
        self._corpus = list(corpus)
        self._provider = provider
        self.name = f"semantic:{provider.name}"
        self._vectors = provider.encode([item.text for item in self._corpus])
        if len(self._vectors) != len(self._corpus):
            raise EvaluationGateError(
                "embedding provider returned a different number of vectors"
            )

    def retrieve(self, query: str, k: int) -> RetrievalResponse:
        query_vectors = self._provider.encode([query])
        if len(query_vectors) != 1:
            raise EvaluationGateError(
                "embedding provider must return exactly one query vector"
            )
        query_vector = query_vectors[0]

        scored = [
            (_cosine(query_vector, vector), item)
            for item, vector in zip(self._corpus, self._vectors)
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].evidence_id))
        return RetrievalResponse(
            hits=[
                BenchmarkHit(
                    evidence_id=item.evidence_id,
                    source_id=item.source_id,
                    structure_node_ids=item.structure_node_ids,
                    score=score,
                )
                for score, item in scored[:k]
            ],
            estimated_cost_usd=0.0,
        )


def evaluate_retrievers(
    *,
    source_id: str,
    logical_source_id: str,
    queries: Sequence[BenchmarkQuery],
    evidence: Sequence[SourceEvidenceBlock],
    link_store: EvidenceLinkStore,
    retrievers: Iterable[Retriever],
    k: int = 10,
) -> tuple[RetrievalEvaluationReport, dict[str, list[BenchmarkRunRecord]]]:
    corpus = build_grounded_corpus(evidence, link_store)
    if not corpus:
        raise EvaluationGateError("no grounded text evidence is available")
    if not queries:
        raise EvaluationGateError("no resolved benchmark queries are available")

    summaries: list[BenchmarkSummary] = []
    runs_by_name: dict[str, list[BenchmarkRunRecord]] = {}
    no_hit_queries: dict[str, int] = {}
    for retriever in retrievers:
        runs = run_benchmark(queries, retriever, k=k)
        runs_by_name[retriever.name] = runs
        no_hit_queries[retriever.name] = sum(not run.hits for run in runs)
        summaries.append(summarize_run(queries, runs))

    languages = Counter(query.language or "unknown" for query in queries)
    report = RetrievalEvaluationReport(
        source_id=source_id,
        logical_source_id=logical_source_id,
        queries=len(queries),
        languages=dict(sorted(languages.items())),
        alignment=alignment_coverage(evidence, link_store),
        no_hit_queries=no_hit_queries,
        summaries=summaries,
    )
    return report, runs_by_name


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return _TOKEN_RE.findall(normalized)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise EvaluationGateError("query/document embedding dimensions differ")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
