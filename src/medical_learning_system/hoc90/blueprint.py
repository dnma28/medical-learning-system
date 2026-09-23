from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .session import SourceSpineRef
from ..source_map import LearningValue


class BlueprintStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"


class MasteryTarget(BaseModel):
    concept_id: str = Field(min_length=1)
    target_level: str = Field(pattern=r"^M[0-7]$")
    evidence_required: list[str] = Field(default_factory=list)


class Hoc90Blueprint(BaseModel):
    """Machine navigation blueprint for one adaptive HỌC90 session."""

    lesson_id: str = Field(min_length=1)
    status: BlueprintStatus = BlueprintStatus.DRAFT
    curriculum_position: str | None = None

    source_spine: list[SourceSpineRef] = Field(min_length=1)

    learning_objectives: list[str] = Field(min_length=1)
    mastery_targets: list[MasteryTarget] = Field(default_factory=list)

    required_prerequisites: list[str] = Field(default_factory=list)
    supporting_prerequisites: list[str] = Field(default_factory=list)
    retrieval_targets: list[str] = Field(default_factory=list)
    student_model_snapshot: dict[str, object] = Field(default_factory=dict)
    open_error_ids: list[str] = Field(default_factory=list)

    socratic_chain: list[str] = Field(default_factory=list)
    hint_ladder: list[str] = Field(
        default_factory=lambda: [
            "directional_principle",
            "narrow_or_eliminate",
            "near_complete_scaffold",
        ]
    )
    new_knowledge_mini_lecture_gate: bool = True
    misconception_watch: list[str] = Field(default_factory=list)

    feynman_checkpoint: list[str] = Field(default_factory=list)
    counterfactuals: list[str] = Field(default_factory=list)
    clinical_transfer: list[str] = Field(default_factory=list)
    critical_thinking_probe: list[str] = Field(default_factory=list)

    freshness_requirements: list[str] = Field(default_factory=list)
    completion_gate: list[str] = Field(min_length=1)
    return_to_source_spine: str | None = None
    post_lesson_updates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_policy(self) -> "Hoc90Blueprint":
        needs_freshness = any(
            ref.learning_value == LearningValue.CURRENT_CLINICAL_CHECK
            or ref.freshness_required
            for ref in self.source_spine
        )
        if needs_freshness and not self.freshness_requirements:
            raise ValueError(
                "time-sensitive source targets require freshness_requirements"
            )

        if self.return_to_source_spine is not None:
            routing_keys = {ref.routing_key for ref in self.source_spine}
            logical_ids = {ref.logical_source_id for ref in self.source_spine}
            if (
                self.return_to_source_spine not in routing_keys
                and self.return_to_source_spine not in logical_ids
            ):
                raise ValueError(
                    "return_to_source_spine must reference a source in source_spine"
                )

        return self

    @property
    def primary_source(self) -> SourceSpineRef:
        return self.source_spine[0]


class BlueprintRecord(BaseModel):
    lesson_id: str
    status: BlueprintStatus
    curriculum_position: str | None = None
    source_spine: list[SourceSpineRef] = Field(default_factory=list)
    blueprint: Hoc90Blueprint
