from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    dimension: int | None

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def encode_query(self, text: str) -> list[float]: ...


class SentenceTransformerProvider:
    """Optional local embedding provider for benchmark experiments."""

    def __init__(
        self,
        model_name: str,
        *,
        normalize_embeddings: bool = True,
        device: str | None = None,
        query_template: str = "{text}",
        document_template: str = "{text}",
        trust_remote_code: bool = False,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Local embedding benchmark support is not installed. "
                "Install with: pip install -e '.[embedding-local]'"
            ) from exc

        if "{text}" not in query_template or "{text}" not in document_template:
            raise ValueError("embedding templates must contain {text}")

        self.name = model_name
        self._normalize_embeddings = normalize_embeddings
        self._query_template = query_template
        self._document_template = document_template
        self._model = SentenceTransformer(
            model_name,
            device=device,
            trust_remote_code=trust_remote_code,
        )
        self.dimension = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Backward-compatible alias for document encoding."""
        return self.encode_documents(texts)

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(
            [self._document_template.format(text=text) for text in texts]
        )

    def encode_query(self, text: str) -> list[float]:
        values = self._encode([self._query_template.format(text=text)])
        if len(values) != 1:
            raise ValueError("embedding provider returned unexpected query vector count")
        return values[0]

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        values = self._model.encode(
            list(texts),
            normalize_embeddings=self._normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [row.tolist() for row in values]
