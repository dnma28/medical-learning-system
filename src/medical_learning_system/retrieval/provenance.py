from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedEvidence:
    source_id: str
    text: str
    page: int | None = None
    chapter: str | None = None
    modality: str = "text"
    score: float | None = None
