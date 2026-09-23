from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..source_map import LearningValue


class SourceTarget(BaseModel):
    logical_source_id: str = Field(min_length=1)
    source_map_node_id: str = Field(min_length=1)
    learning_value: LearningValue
    freshness_required: bool = False
    source_anchor: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_freshness(self) -> "SourceTarget":
        if (
            self.learning_value == LearningValue.CURRENT_CLINICAL_CHECK
            and not self.freshness_required
        ):
            raise ValueError(
                "CURRENT_CLINICAL_CHECK source targets require freshness verification"
            )
        return self


class Hoc90Blueprint(BaseModel):
    """Machine navigation blueprint for one adaptive HỌC90 session.

    The blueprint is not a substitute for the source text. It identifies what
    to retrieve and how to adapt the session around the learner state.
    """

    lesson_id: str = Field(min_length=1)
    curriculum_position: str = Field(min_length=1)

    source_spine: list[str] = Field(min_length=1)
    source_targets: list[SourceTarget] = Field(min_length=1)

    learning_objectives: list[str] = Field(default_factory=list)
    mastery_targets: list[str] = Field(default_factory=list)

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
    completion_gate: list[str] = Field(default_factory=list)
    return_to_source_spine: str | None = None
    post_lesson_updates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_targets(self) -> "Hoc90Blueprint":
        spine = set(self.source_spine)
        outside = [
            target.logical_source_id
            for target in self.source_targets
            if target.logical_source_id not in spine
        ]
        if outside:
            raise ValueError(
                "all source_targets must belong to a logical book in source_spine"
            )

        if self.return_to_source_spine is not None and self.return_to_source_spine not in spine:
            raise ValueError("return_to_source_spine must belong to source_spine")

        return self


class BlueprintRecord(BaseModel):
    lesson_id: str
    status: str
    curriculum_position: str | None = None
    source_spine: list[str] = Field(default_factory=list)
    blueprint: Hoc90Blueprint
