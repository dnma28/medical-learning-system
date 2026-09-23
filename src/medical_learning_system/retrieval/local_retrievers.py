from __future__ import annotations

import math
import re
import sqlite3
from collections.abc import Sequence

from .benchmark import BenchmarkHit, RetrievalResponse
from .embedding_providers import EmbeddingProvider
from ..evidence_alignment import EvidenceLinkStore
from ..evidence_store import EvidenceStore, SourceEvidenceBlock


class LocalKeywordRetriever:
    name = "local-keyword-fts5"

    def __init__(self, evidence_store: EvidenceStore, link_store: EvidenceLinkStore, source_id: str):
        self._evidence = {
            block.evidence_id: block
            for block in evidence_store.list_source(source_id)
            if block.text and block.text.strip()
        }
        self._links = {
            evidence_id: {link.node_id for link in link_store.list_evidence(evidence_id)}
            for evidence_id in self._evidence
        }
        self._db = sqlite3.connect(":memory:")
        self._db.execute(
            "CREATE VIRTUAL TABLE evidence_fts USING fts5(evidence_id UNINDEXED, text, tokenize='unicode61')"
        )
        self._db.executemany(
            "INSERT INTO evidence_fts (evidence_id, text) VALUES (?, ?)",
            [(block.evidence_id, block.text) for block in self._evidence.values()],
        )

    def retrieve(self, query: str, k: int) -> RetrievalResponse:
        if k < 1:
            raise ValueError("k must be >= 1")
        match_query = _fts_query(query)
        if not match_query:
            return RetrievalResponse(hits=[])

        rows = self._db.execute(
            """
            SELECT evidence_id, bm25(evidence_fts) AS rank
            FROM evidence_fts
            WHERE evidence_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match_query, k),
        ).fetchall()

        return RetrievalResponse(
            hits=[
                _benchmark_hit(
                    self._evidence[evidence_id],
                    self._links.get(evidence_id, set()),
                    score=-float(rank),
                )
                for evidence_id, rank in rows
            ],
            estimated_cost_usd=0.0,
        )


class LocalSemanticRetriever:
    def __init__(
        self,
        evidence_store: EvidenceStore,
        link_store: EvidenceLinkStore,
        source_id: str,
        provider: EmbeddingProvider,
    ):
        self.provider = provider
        self.name = f"local-semantic:{provider.name}"
        self._evidence = [
            block
            for block in evidence_store.list_source(source_id)
            if block.text and block.text.strip()
        ]
        self._links = {
            block.evidence_id: {link.node_id for link in link_store.list_evidence(block.evidence_id)}
            for block in self._evidence
        }
        texts = [block.text or "" for block in self._evidence]
        self._vectors = provider.encode(texts) if texts else []
        if len(self._vectors) != len(self._evidence):
            raise ValueError("embedding provider returned unexpected vector count")

    def retrieve(self, query: str, k: int) -> RetrievalResponse:
        if k < 1:
            raise ValueError("k must be >= 1")
        if not self._evidence:
            return RetrievalResponse(hits=[])

        query_vectors = self.provider.encode([query])
        if len(query_vectors) != 1:
            raise ValueError("embedding provider must return one query vector")
        query_vector = query_vectors[0]

        ranked = sorted(
            (
                (_cosine(query_vector, vector), block)
                for block, vector in zip(self._evidence, self._vectors)
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:k]

        return RetrievalResponse(
            hits=[
                _benchmark_hit(
                    block,
                    self._links.get(block.evidence_id, set()),
                    score=score,
                )
                for score, block in ranked
            ],
            estimated_cost_usd=0.0,
        )


def _benchmark_hit(
    block: SourceEvidenceBlock,
    structure_node_ids: set[str],
    *,
    score: float,
) -> BenchmarkHit:
    return BenchmarkHit(
        evidence_id=block.evidence_id,
        source_id=block.source_id,
        structure_node_ids=structure_node_ids,
        score=score,
    )


def _fts_query(value: str) -> str:
    tokens = [token for token in re.findall(r"\w+", value.casefold(), flags=re.UNICODE) if token]
    return " OR ".join(f'"{token}"' for token in tokens)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    if not left:
        raise ValueError("embedding vector cannot be empty")

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
