from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from ..source_map import LearningValue


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class LearningEventType(str, Enum):
    RETRIEVAL = "retrieval"
    SOCRATIC_RESPONSE = "socratic_response"
    HINT = "hint"
    SELF_CORRECTION = "self_correction"
    EXPLANATION = "explanation"
    FEYNMAN = "feynman"
    COUNTERFACTUAL = "counterfactual"
    TRANSFER = "transfer"
    CLINICAL_TRANSFER = "clinical_transfer"
    ERROR_OBSERVED = "error_observed"
    SOURCE_RETRIEVAL = "source_retrieval"
    SOURCE_GAP = "source_gap"
    CHECKPOINT = "checkpoint"


class SessionStage(BaseModel):
    name: str
    minutes: int = Field(gt=0)
    objective: str


class SourceSpineRef(BaseModel):
    """Source-aware HỌC90 pointer.

    logical_source_id identifies the book. A Source Map node is preferred,
    while source_id and source_anchor retain exact physical provenance when
    known. Legacy sessions may still store simple strings in source_spine.
    """

    logical_source_id: str = Field(min_length=1)
    source_map_node_id: str | None = None
    source_id: str | None = None
    source_anchor: dict[str, Any] = Field(default_factory=dict)
    learning_value: LearningValue = LearningValue.CORE_MASTERY
    freshness_required: bool = False

    @model_validator(mode="after")
    def validate_freshness(self) -> "SourceSpineRef":
        if (
            self.learning_value == LearningValue.CURRENT_CLINICAL_CHECK
            and not self.freshness_required
        ):
            raise ValueError(
                "CURRENT_CLINICAL_CHECK source refs require freshness verification"
            )
        return self

    @property
    def routing_key(self) -> str:
        if self.source_map_node_id:
            return f"{self.logical_source_id}:{self.source_map_node_id}"
        return self.logical_source_id


class SessionCheckpoint(BaseModel):
    concept_id: str | None = None
    question_id: str | None = None
    hint_level: int = Field(default=0, ge=0, le=3)
    toc_position: str | None = None
    source_ref: SourceSpineRef | None = None
    current_branch: str | None = None
    return_to_source: str | None = None
    working_mastery_delta: dict[str, Any] = Field(default_factory=dict)
    open_error_ids: list[str] = Field(default_factory=list)
    saved_at: datetime = Field(default_factory=_utcnow)


class LearningEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    event_type: LearningEventType
    concept_id: str | None = None
    question_id: str | None = None
    source_ref: SourceSpineRef | None = None
    outcome: str | None = None
    answer_summary: str | None = None
    hint_level: int = Field(default=0, ge=0, le=3)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class Hoc90Session(BaseModel):
    topic: str
    target_outcome: str
    stages: list[SessionStage]

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    status: SessionStatus = SessionStatus.PLANNED
    curriculum_position: str | None = None

    # Backward compatible: old rows contain strings; new rows may carry
    # structured SourceSpineRef objects.
    source_spine: list[str | SourceSpineRef] = Field(default_factory=list)
    toc_position: str | None = None
    checkpoint: SessionCheckpoint | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def total_minutes(self) -> int:
        return sum(stage.minutes for stage in self.stages)

    def is_90_minutes(self) -> bool:
        return self.total_minutes == 90

    def primary_source_ref(self) -> SourceSpineRef | None:
        for item in self.source_spine:
            if isinstance(item, SourceSpineRef):
                return item
        return None

    def start(self) -> "Hoc90Session":
        now = _utcnow()
        return self.model_copy(
            update={
                "status": SessionStatus.ACTIVE,
                "started_at": self.started_at or now,
                "updated_at": now,
            }
        )

    def pause(self, checkpoint: SessionCheckpoint) -> "Hoc90Session":
        return self.model_copy(
            update={
                "status": SessionStatus.PAUSED,
                "checkpoint": checkpoint,
                "toc_position": checkpoint.toc_position or self.toc_position,
                "updated_at": _utcnow(),
            }
        )

    def resume(self) -> "Hoc90Session":
        return self.model_copy(
            update={
                "status": SessionStatus.ACTIVE,
                "updated_at": _utcnow(),
            }
        )

    def complete(self) -> "Hoc90Session":
        now = _utcnow()
        return self.model_copy(
            update={
                "status": SessionStatus.COMPLETED,
                "completed_at": now,
                "updated_at": now,
            }
        )
