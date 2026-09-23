from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from .embedding_providers import SentenceTransformerProvider


class EmbeddingCandidate(BaseModel):
    candidate_id: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    expected_dimension: int = Field(gt=0)
    max_input_tokens: int | None = Field(default=None, gt=0)
    language_scope: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    query_template: str = "{text}"
    document_template: str = "{text}"
    normalize_embeddings: bool = True
    trust_remote_code: bool = False
    role: str = "candidate"
    verified_at: date
    notes: str | None = None

    @model_validator(mode="after")
    def templates_have_text_placeholder(self) -> "EmbeddingCandidate":
        for name, template in (
            ("query_template", self.query_template),
            ("document_template", self.document_template),
        ):
            if "{text}" not in template:
                raise ValueError(f"{name} must contain {{text}}")
        return self

    def format_query(self, text: str) -> str:
        return self.query_template.format(text=text)

    def format_document(self, text: str) -> str:
        return self.document_template.format(text=text)


class EmbeddingCandidateRegistry(BaseModel):
    candidates: list[EmbeddingCandidate]

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> "EmbeddingCandidateRegistry":
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate embedding candidate_id")
        return self

    def get(self, candidate_id: str) -> EmbeddingCandidate:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise KeyError(candidate_id)


def load_embedding_candidates(path: Path) -> EmbeddingCandidateRegistry:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return EmbeddingCandidateRegistry.model_validate(payload)


def build_candidate_provider(
    candidate: EmbeddingCandidate,
    *,
    device: str | None = None,
) -> SentenceTransformerProvider:
    provider = SentenceTransformerProvider(
        candidate.model_name,
        normalize_embeddings=candidate.normalize_embeddings,
        device=device,
        query_template=candidate.query_template,
        document_template=candidate.document_template,
        trust_remote_code=candidate.trust_remote_code,
    )
    if (
        provider.dimension is not None
        and provider.dimension != candidate.expected_dimension
    ):
        raise ValueError(
            f"{candidate.candidate_id}: expected dimension "
            f"{candidate.expected_dimension}, got {provider.dimension}"
        )
    return provider
