from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RAGConfig:
    working_dir: Path = Path("./rag_storage")
    parser: str = "mineru"
    parse_method: str = "auto"
    enable_image_processing: bool = True
    enable_table_processing: bool = True
    enable_equation_processing: bool = True


class RAGAnythingAdapter:
    """Boundary around RAG-Anything.

    RAG output is retrieval/candidate evidence only. It must never be written
    directly into the canonical medical knowledge graph.
    """

    def __init__(self, config: RAGConfig):
        self.config = config
        self._engine: Any | None = None

    def dependency_available(self) -> bool:
        try:
            import raganything  # noqa: F401
        except ImportError:
            return False
        return True

    def build_engine(
        self,
        *,
        llm_model_func: Any,
        vision_model_func: Any,
        embedding_func: Any,
    ) -> Any:
        if not self.dependency_available():
            raise RuntimeError(
                "RAG-Anything is not installed. Install with: pip install -e '.[rag]'"
            )

        from raganything import RAGAnything, RAGAnythingConfig

        rag_config = RAGAnythingConfig(
            working_dir=str(self.config.working_dir),
            parser=self.config.parser,
            parse_method=self.config.parse_method,
            enable_image_processing=self.config.enable_image_processing,
            enable_table_processing=self.config.enable_table_processing,
            enable_equation_processing=self.config.enable_equation_processing,
        )
        self._engine = RAGAnything(
            config=rag_config,
            llm_model_func=llm_model_func,
            vision_model_func=vision_model_func,
            embedding_func=embedding_func,
        )
        return self._engine
