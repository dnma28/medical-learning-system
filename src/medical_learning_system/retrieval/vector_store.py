from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..evidence_store import SourceEvidenceBlock


class EvidenceEmbedding(BaseModel):
    evidence_id: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    embedding_dim: int = Field(gt=0)
    embedding: list[float]
    content_sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def dimensions_match(self) -> "EvidenceEmbedding":
        if len(self.embedding) != self.embedding_dim:
            raise ValueError("embedding length must equal embedding_dim")
        return self


class RetrievalHit(BaseModel):
    evidence_id: str
    source_id: str
    structure_node_id: str | None = None
    structure_node_ids: set[str] = Field(default_factory=set)
    page_index: int = Field(ge=0)
    content_type: str
    text: str | None = None
    score: float


class SupabaseRetrievalStore:
    """Model-aware pgvector + keyword retrieval over source evidence."""

    EMBEDDINGS = "mls_evidence_embeddings"

    def __init__(self, client: Any):
        self.client = client

    def upsert_embedding(self, record: EvidenceEmbedding) -> None:
        self.client.table(self.EMBEDDINGS).upsert(
            record.model_dump(),
            on_conflict="evidence_id,embedding_model",
        ).execute()

    def needs_embedding(
        self,
        evidence: SourceEvidenceBlock,
        embedding_model: str,
    ) -> bool:
        response = (
            self.client.table(self.EMBEDDINGS)
            .select("content_sha256")
            .eq("evidence_id", evidence.evidence_id)
            .eq("embedding_model", embedding_model)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return not rows or rows[0].get("content_sha256") != evidence.content_sha256

    def semantic_search(
        self,
        *,
        query_embedding: list[float],
        embedding_model: str,
        match_count: int = 8,
        source_ids: list[str] | None = None,
    ) -> list[RetrievalHit]:
        if not query_embedding:
            raise ValueError("query_embedding cannot be empty")
        if match_count < 1:
            raise ValueError("match_count must be >= 1")

        response = self.client.rpc(
            "mls_match_evidence",
            {
                "query_embedding": query_embedding,
                "embedding_model_filter": embedding_model,
                "match_count": match_count,
                "source_ids": source_ids,
            },
        ).execute()
        return [
            RetrievalHit(
                evidence_id=row["evidence_id"],
                source_id=row["source_id"],
                structure_node_id=_legacy_structure_node_id(row),
                structure_node_ids=set(row.get("structure_node_ids") or []),
                page_index=row["page_index"],
                content_type=row["content_type"],
                text=row.get("text"),
                score=float(row["similarity"]),
            )
            for row in _data(response)
        ]

    def keyword_search(
        self,
        query_text: str,
        *,
        match_count: int = 8,
        source_ids: list[str] | None = None,
    ) -> list[RetrievalHit]:
        if not query_text.strip():
            raise ValueError("query_text cannot be empty")
        if match_count < 1:
            raise ValueError("match_count must be >= 1")

        response = self.client.rpc(
            "mls_keyword_evidence",
            {
                "query_text": query_text,
                "match_count": match_count,
                "source_ids": source_ids,
            },
        ).execute()
        return [
            RetrievalHit(
                evidence_id=row["evidence_id"],
                source_id=row["source_id"],
                structure_node_id=_legacy_structure_node_id(row),
                structure_node_ids=set(row.get("structure_node_ids") or []),
                page_index=row["page_index"],
                content_type=row["content_type"],
                text=row.get("text"),
                score=float(row["rank"]),
            )
            for row in _data(response)
        ]


def _data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    return list(data or [])


def _legacy_structure_node_id(row: dict[str, Any]) -> str | None:
    """Keep the legacy scalar only when the alignment is unambiguous."""
    explicit = row.get("structure_node_id")
    if explicit:
        return str(explicit)
    node_ids = list(dict.fromkeys(row.get("structure_node_ids") or []))
    return node_ids[0] if len(node_ids) == 1 else None
