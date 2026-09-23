from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MasteryState(str, Enum):
    """Legacy coarse state retained for backward compatibility."""

    NEW = "new"
    FRAGILE = "fragile"
    DEVELOPING = "developing"
    STABLE = "stable"


class MasteryLevel(str, Enum):
    """Evidence-based HỌC90 mastery ladder."""

    M0 = "M0"
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"
    M5 = "M5"
    M6 = "M6"
    M7 = "M7"


class ErrorType(str, Enum):
    CONCEPT_ERROR = "concept_error"
    CAUSAL_ERROR = "causal_error"
    LEVEL_ERROR = "level_error"
    OVERGENERALIZATION = "overgeneralization"
    MISSING_CONDITION = "missing_condition"
    TERMINOLOGY_ERROR = "terminology_error"
    ASSUMPTION_AS_FACT = "assumption_as_fact"
    INFERENCE_LEAP = "inference_leap"
    SOURCE_CONFUSION = "source_confusion"
    TRANSFER_FAILURE = "transfer_failure"
    PREREQUISITE_GAP = "prerequisite_gap"


class ErrorStatus(str, Enum):
    OPEN = "open"
    SELF_CORRECTED = "self_corrected"
    RETEST_REQUIRED = "retest_required"
    CORRECTED = "corrected"
    CLOSED_DURABLE = "closed_durable"
    DEPRECATED = "deprecated"


class ConceptMastery(BaseModel):
    concept_id: str

    # Keep the original coarse field so old callers remain valid.
    state: MasteryState = MasteryState.NEW

    mastery_level: MasteryLevel = MasteryLevel.M0
    historical_peak_mastery: MasteryLevel = MasteryLevel.M0
    current_strength: float = Field(default=0.0, ge=0.0, le=1.0)

    retrieval_successes: int = Field(default=0, ge=0)
    retrieval_failures: int = Field(default=0, ge=0)

    last_exposure: datetime | None = None
    last_independent_retrieval: datetime | None = None
    next_review: datetime | None = None

    mechanism_explained_independently: bool = False
    feynman_pass: bool = False
    counterfactual_pass: bool = False
    transfer_pass: bool = False
    clinical_transfer_pass: bool = False
    integration_pass: bool = False

    open_error_ids: list[str] = Field(default_factory=list)
    evidence_for_mastery: list[str] = Field(default_factory=list)
    source_contexts_seen: list[str] = Field(default_factory=list)

    updated_at: datetime = Field(default_factory=_utcnow)


class LearnerError(BaseModel):
    id: str
    concept_id: str
    statement: str

    # Legacy field retained; v6 uses it as the current correction explanation.
    correction: str | None = None
    resolved: bool = False

    error_type: ErrorType = ErrorType.CONCEPT_ERROR
    status: ErrorStatus = ErrorStatus.OPEN
    underlying_gap: str | None = None
    contexts: list[str] = Field(default_factory=list)
    hint_response: str | None = None
    next_probe: str | None = None

    times_seen: int = Field(default=1, ge=1)
    first_seen: datetime = Field(default_factory=_utcnow)
    last_seen: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def mark_seen(self, *, context: str | None = None) -> "LearnerError":
        contexts = list(self.contexts)
        if context and context not in contexts:
            contexts.append(context)
        return self.model_copy(
            update={
                "times_seen": self.times_seen + 1,
                "last_seen": _utcnow(),
                "updated_at": _utcnow(),
                "contexts": contexts,
            }
        )
