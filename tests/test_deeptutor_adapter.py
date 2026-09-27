from medical_learning_system.deeptutor_adapter import (
    DeepTutorCapability,
    DeepTutorHoc90Adapter,
)
from medical_learning_system.learning.router import (
    AdaptiveAction,
    QualityMode,
    RoutingDecision,
)


def _decision(action: AdaptiveAction) -> RoutingDecision:
    return RoutingDecision(
        action=action,
        quality_mode=QualityMode.DEEP,
        reason="test",
        target_ids=["concept-1"],
        return_to_source_spine="Guyton ch2",
    )


def test_retrieval_routes_to_question_generation_without_state_write():
    task = DeepTutorHoc90Adapter().build_task(
        _decision(AdaptiveAction.START_RETRIEVAL),
        source_context=["verified passage"],
    )
    assert task.capability == DeepTutorCapability.DEEP_QUESTION
    assert task.source_context == ["verified passage"]
    assert task.may_write_learner_state is False
    assert task.may_write_medical_truth is False


def test_source_spine_routes_to_guided_learning():
    task = DeepTutorHoc90Adapter().build_task(
        _decision(AdaptiveAction.CONTINUE_SOURCE_SPINE)
    )
    assert task.capability == DeepTutorCapability.GUIDED_LEARNING


def test_current_evidence_stays_under_mls_control():
    task = DeepTutorHoc90Adapter().build_task(
        _decision(AdaptiveAction.VERIFY_CURRENT_EVIDENCE)
    )
    assert task.capability == DeepTutorCapability.AGENT_LOOP
    assert any("current clinical" in item for item in task.instructions)
