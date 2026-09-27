from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from ..hoc90.session import LearningEvent, LearningEventType, SourceSpineRef
from .models import MasteryLevel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClinicalReasoningFramework(str, Enum):
    ILLNESS_SCRIPT = "illness_script"
    HOAC_II = "hoac_ii"
    SCT_STYLE = "sct_style"


class SkillNode(BaseModel):
    """One learner-skill node. It is not medical truth or curriculum position."""

    skill_node_id: str = Field(min_length=1)
    vi_name: str = Field(min_length=1)
    english_alias: str | None = None
    domain: str = Field(min_length=1)
    parent_ids: list[str] = Field(default_factory=list)
    required_prerequisites: list[str] = Field(default_factory=list)
    supporting_prerequisites: list[str] = Field(default_factory=list)
    unlock_rule: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=_utcnow)


class SkillState(BaseModel):
    """Evidence-derived learner state for a Skill Tree node."""

    skill_node_id: str = Field(min_length=1)
    mastery_level: MasteryLevel = MasteryLevel.M0
    current_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    forgetting_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    open_error_ids: list[str] = Field(default_factory=list)
    last_test: datetime | None = None
    next_review: datetime | None = None
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=_utcnow)


class ClinicalReasoningTask(BaseModel):
    """Source-bounded task contract for advanced clinical reasoning practice."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    framework: ClinicalReasoningFramework
    skill_node_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    concept_ids: list[str] = Field(default_factory=list)
    source_routing_keys: list[str] = Field(min_length=1)
    current_validity_required: bool = False
    current_validity_verified: bool = False

    @model_validator(mode="after")
    def validate_current_validity(self) -> "ClinicalReasoningTask":
        if self.current_validity_required and not self.current_validity_verified:
            raise ValueError(
                "Time-sensitive clinical tasks require current-validity verification "
                "before learner presentation."
            )
        return self


class ClinicalReasoningEvidence(BaseModel):
    """Assessment evidence only; never an automatic mastery decision."""

    task_id: str = Field(min_length=1)
    framework: ClinicalReasoningFramework
    skill_node_id: str = Field(min_length=1)
    response_summary: str = Field(min_length=1)
    outcome: str | None = None
    criteria_met: list[str] = Field(default_factory=list)
    criteria_missed: list[str] = Field(default_factory=list)
    assisted: bool = False
    expert_panel_id: str | None = None
    standardized_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sct_scoring(self) -> "ClinicalReasoningEvidence":
        if (
            self.framework == ClinicalReasoningFramework.SCT_STYLE
            and self.standardized_score is not None
            and not self.expert_panel_id
        ):
            raise ValueError(
                "SCT-style standardized scoring requires an explicit expert-panel reference."
            )
        return self


def build_clinical_transfer_event(
    *,
    session_id: str,
    task: ClinicalReasoningTask,
    evidence: ClinicalReasoningEvidence,
    source_ref: SourceSpineRef | None = None,
    hint_level: int = 0,
) -> LearningEvent:
    """Convert one reviewed clinical-reasoning response into append-only evidence.

    This function does not update ConceptMastery or SkillState. A separate
    evidence policy must decide whether and how the event changes learner state.
    """

    if evidence.task_id != task.task_id:
        raise ValueError("Evidence task_id does not match the clinical reasoning task.")
    if evidence.framework != task.framework:
        raise ValueError("Evidence framework does not match the clinical reasoning task.")
    if evidence.skill_node_id != task.skill_node_id:
        raise ValueError("Evidence skill_node_id does not match the task.")

    concept_id = task.concept_ids[0] if task.concept_ids else None
    return LearningEvent(
        session_id=session_id,
        event_type=LearningEventType.CLINICAL_TRANSFER,
        concept_id=concept_id,
        source_ref=source_ref,
        outcome=evidence.outcome,
        answer_summary=evidence.response_summary,
        hint_level=hint_level,
        metadata={
            "clinical_reasoning_framework": task.framework.value,
            "skill_node_id": task.skill_node_id,
            "task_id": task.task_id,
            "concept_ids": list(task.concept_ids),
            "source_routing_keys": list(task.source_routing_keys),
            "current_validity_required": task.current_validity_required,
            "current_validity_verified": task.current_validity_verified,
            "criteria_met": list(evidence.criteria_met),
            "criteria_missed": list(evidence.criteria_missed),
            "assisted": evidence.assisted or hint_level > 0,
            "expert_panel_id": evidence.expert_panel_id,
            "standardized_score": evidence.standardized_score,
            "automatic_mastery_credit": False,
        },
    )
