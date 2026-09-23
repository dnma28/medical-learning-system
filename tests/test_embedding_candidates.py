from pathlib import Path

import pytest
from pydantic import ValidationError

from medical_learning_system.retrieval.embedding_candidates import (
    EmbeddingCandidate,
    load_embedding_candidates,
)


def registry_path() -> Path:
    return Path("config/embedding_candidates.yaml")


def test_candidate_registry_loads_without_downloading_models():
    registry = load_embedding_candidates(registry_path())

    assert {candidate.candidate_id for candidate in registry.candidates} == {
        "bge-m3",
        "multilingual-e5-large-instruct",
        "gte-multilingual-base",
        "pubmedbert-base-embeddings",
    }
    assert registry.get("bge-m3").expected_dimension == 1024
    assert registry.get("gte-multilingual-base").expected_dimension == 768


def test_e5_candidate_formats_query_and_document_asymmetrically():
    candidate = load_embedding_candidates(registry_path()).get(
        "multilingual-e5-large-instruct"
    )

    query = candidate.format_query("Vì sao K+ ảnh hưởng điện thế nghỉ?")
    document = candidate.format_document("Resting membrane potential")

    assert query.startswith("Instruct:")
    assert "\nQuery: Vì sao K+" in query
    assert document == "Resting membrane potential"


def test_candidate_template_must_keep_text_placeholder():
    with pytest.raises(ValidationError, match="query_template"):
        EmbeddingCandidate(
            candidate_id="bad",
            model_name="example/model",
            expected_dimension=8,
            language_scope="test",
            query_template="missing placeholder",
            verified_at="2026-09-23",
        )
