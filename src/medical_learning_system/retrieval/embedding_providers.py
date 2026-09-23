from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    dimension: int | None

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerProvider:
    """Optional local embedding provider for benchmark experiments."""

    def __init__(
        self,
        model_name: str,
        *,
        normalize_embeddings: bool = True,
        device: str | None = None,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Local embedding benchmark support is not installed. "
                "Install with: pip install -e '.[embedding-local]'"
            ) from exc

        self.name = model_name
        self._normalize_embeddings = normalize_embeddings
        self._model = SentenceTransformer(model_name, device=device)
        self.dimension = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        values = self._model.encode(
            list(texts),
            normalize_embeddings=self._normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [row.tolist() for row in values]
