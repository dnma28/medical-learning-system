from datetime import datetime, timezone

import pytest

from medical_learning_system.hoc90.session import LearningEventType, SourceSpineRef
from medical_learning_system.source_map import LearningValue
from medical_learning_system.student.models import MasteryLevel
from medical_learning_system.student.skills import (
    ClinicalReasoningEvidence,
    ClinicalReasoningFramework,
    ClinicalReasoningTask,
    SkillNode,
    SkillState,
    build_clinical_transfer_event,
)


def task(**updates) -> ClinicalReasoningTask:
    data = {
        "task_id": "clinical-task-1",
        "framework": ClinicalReasoningFramework.HOAC_II,
        "skill_node_id": "clinical-reasoning:hoac-ii",
        "prompt": "Analyze the source-bounded rehabilitation case.",
        "concept_ids": ["load-tolerance"],
        "source_routing_keys": ["magee:chapter"],
    }
    data.update(updates)
    return ClinicalReasoningTask(**data)


def evidence(**updates) -> ClinicalReasoningEvidence:
    data = {
        "task_id": "clinical-task-1",
        "framework": ClinicalReasoningFramework.HOAC_II,
        "skill_node_id": "clinical-reasoning:hoac-ii",
        "response_summary": "Learner linked an impairment hypothesis to a functional problem.",
        "outcome": "partial",
        "criteria_met": ["hypothesis_stated"],
        "criteria_missed": ["reassessment_criterion"],
    }
    data.update(updates)
    return ClinicalReasoningEvidence(**data)


def test_clinical_reasoning_event_is_evidence_not_mastery_credit():
    source_ref = SourceSpineRef(
        logical_source_id="magee-orthopedic-physical-assessment",
        source_map_node_id="chapter",
        source_id="magee--physical",
        source_anchor={"page_start": 1},
        learning_value=LearningValue.CORE_MASTERY,
    )

    event = build_clinical_transfer_event(
        session_id="session-1",
        task=task(),
        evidence=evidence(),
        source_ref=source_ref,
    )

    assert event.event_type == LearningEventType.CLINICAL_TRANSFER
    assert event.concept_id == "load-tolerance"
    assert event.metadata["clinical_reasoning_framework"] == "hoac_ii"
    assert event.metadata["skill_node_id"] == "clinical-reasoning:hoac-ii"
    assert event.metadata["automatic_mastery_credit"] is False
    assert event.source_ref == source_ref


def test_hints_are_recorded_as_assistance():
    event = build_clinical_transfer_event(
        session_id="session-1",
        task=task(),
        evidence=evidence(),
        hint_level=2,
    )
    assert event.metadata["assisted"] is True
    assert event.hint_level == 2


def test_sct_style_standardized_score_requires_explicit_panel_reference():
    with pytest.raises(ValueError, match="expert-panel"):
        ClinicalReasoningEvidence(
            task_id="sct-1",
            framework=ClinicalReasoningFramework.SCT_STYLE,
            skill_node_id="clinical-reasoning:sct",
            response_summary="New information makes the hypothesis less likely.",
            standardized_score=0.6,
        )

    scored = ClinicalReasoningEvidence(
        task_id="sct-1",
        framework=ClinicalReasoningFramework.SCT_STYLE,
        skill_node_id="clinical-reasoning:sct",
        response_summary="New information makes the hypothesis less likely.",
        expert_panel_id="panel-2026-01",
        standardized_score=0.6,
    )
    assert scored.standardized_score == 0.6


def test_time_sensitive_task_requires_current_validity_gate():
    with pytest.raises(ValueError, match="current-validity"):
        task(
            current_validity_required=True,
            current_validity_verified=False,
        )

    verified = task(
        current_validity_required=True,
        current_validity_verified=True,
    )
    assert verified.current_validity_verified is True


def test_skill_models_match_runtime_state_contract():
    node = SkillNode(
        skill_node_id="clinical-reasoning:illness-script",
        vi_name="Tổ chức bản kịch bệnh học",
        english_alias="Illness Script",
        domain="clinical_reasoning",
        required_prerequisites=["mechanism-explanation"],
    )
    state = SkillState(
        skill_node_id=node.skill_node_id,
        mastery_level=MasteryLevel.M2,
        current_strength=0.4,
        forgetting_risk=0.2,
        last_test=datetime(2026, 9, 27, tzinfo=timezone.utc),
        evidence_summary={"event_ids": ["event-1"]},
    )

    assert node.domain == "clinical_reasoning"
    assert state.mastery_level == MasteryLevel.M2


def test_task_and_evidence_identity_must_match():
    mismatched = evidence(skill_node_id="other-skill")
    with pytest.raises(ValueError, match="skill_node_id"):
        build_clinical_transfer_event(
            session_id="session-1",
            task=task(),
            evidence=mismatched,
        )
