from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class MasteryState(str, Enum):
    NEW = "new"
    FRAGILE = "fragile"
    DEVELOPING = "developing"
    STABLE = "stable"


class ConceptMastery(BaseModel):
    concept_id: str
    state: MasteryState = MasteryState.NEW
    retrieval_successes: int = Field(default=0, ge=0)
    retrieval_failures: int = Field(default=0, ge=0)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class LearnerError(BaseModel):
    id: str
    concept_id: str
    statement: str
    correction: str | None = None
    resolved: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
