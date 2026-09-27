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


def test_free_retrieval_stays_mls_native():
    task = DeepTutorHoc90Adapter().build_task(
        _decision(AdaptiveAction.START_RETRIEVAL),
        source_context=["verified passage"],
    )
    assert task.capability == DeepTutorCapability.MLS_NATIVE
    assert task.may_write_learner_state is False
    assert task.may_write_medical_truth is False
    assert task.automatic_mastery_credit is False


def test_source_spine_routes_to_guided_learning():
    task = DeepTutorHoc90Adapter().build_task(
        _decision(AdaptiveAction.CONTINUE_SOURCE_SPINE),
        source_context=["verified passage"],
    )
    assert task.capability == DeepTutorCapability.GUIDED_LEARNING


def test_prerequisite_repair_can_use_source_grounded_guidance():
    task = DeepTutorHoc90Adapter().build_task(
        _decision(AdaptiveAction.PREREQUISITE_REPAIR),
        source_context=["verified prerequisite passage"],
    )
    assert task.capability == DeepTutorCapability.GUIDED_LEARNING


def test_error_transfer_and_current_evidence_stay_mls_native():
    adapter = DeepTutorHoc90Adapter()
    for action in (
        AdaptiveAction.ERROR_REMEDIATION,
        AdaptiveAction.TRANSFER,
        AdaptiveAction.SOURCE_RECOVERY,
        AdaptiveAction.VERIFY_CURRENT_EVIDENCE,
    ):
        task = adapter.build_task(_decision(action), source_context=["verified passage"])
        assert task.capability == DeepTutorCapability.MLS_NATIVE


def test_reading_quiz_is_explicitly_recognition_only():
    task = DeepTutorHoc90Adapter().build_reading_quiz(
        _decision(AdaptiveAction.CONTINUE_SOURCE_SPINE),
        source_context=["verified passage"],
    )
    assert task.capability == DeepTutorCapability.READING_QUIZ
    assert task.evidence_ceiling == "M1"
    assert task.automatic_mastery_credit is False
