from datetime import datetime, timedelta, timezone

import pytest

from medical_learning_system.hoc90.session import (
    LearningEvent,
    LearningEventType,
)
from medical_learning_system.student.models import ConceptMastery, MasteryLevel
from medical_learning_system.student.spaced_retrieval import (
    FSRS_ENGINE_VERSION,
    FsrsSpacedRetrievalScheduler,
)

NOW = datetime(2026, 9, 27, 2, 0, tzinfo=timezone.utc)


def retrieval_event(
    *,
    event_id: str = "retrieval-1",
    rating: str = "good",
    created_at: datetime = NOW,
    hint_level: int = 0,
    independent: bool = True,
    evidence_kind: str | None = None,
) -> LearningEvent:
    metadata = {
        "retrieval_independent": independent,
        "retrieval_rating": rating,
    }
    if evidence_kind is not None:
        metadata["evidence_kind"] = evidence_kind
    return LearningEvent(
        event_id=event_id,
        session_id="session-1",
        event_type=LearningEventType.RETRIEVAL,
        concept_id="electrochemical-gradient",
        hint_level=hint_level,
        metadata=metadata,
        created_at=created_at,
    )


def test_fsrs_schedules_next_review_without_promoting_mastery():
    scheduler = FsrsSpacedRetrievalScheduler()
    before = ConceptMastery(
        concept_id="electrochemical-gradient",
        mastery_level=MasteryLevel.M3,
        historical_peak_mastery=MasteryLevel.M3,
        current_strength=0.61,
    )

    after = scheduler.apply(mastery=before, event=retrieval_event())

    assert after.mastery_level == MasteryLevel.M3
    assert after.historical_peak_mastery == MasteryLevel.M3
    assert after.current_strength == 0.61
    assert after.retrieval_successes == 1
    assert after.retrieval_failures == 0
    assert after.last_independent_retrieval == NOW
    assert after.next_review is not None
    assert after.next_review > NOW
    assert after.spaced_repetition_state["engine"] == "fsrs"
    assert (
        after.spaced_repetition_state["engine_version"]
        == FSRS_ENGINE_VERSION
    )
    assert after.spaced_repetition_state["fuzzing_enabled"] is False


def test_reapplying_same_event_is_idempotent():
    scheduler = FsrsSpacedRetrievalScheduler()
    first = scheduler.apply(
        mastery=ConceptMastery(concept_id="electrochemical-gradient"),
        event=retrieval_event(),
    )
    second = scheduler.apply(mastery=first, event=retrieval_event())

    assert second.retrieval_successes == 1
    assert second.retrieval_failures == 0
    assert second.next_review == first.next_review
    assert second.spaced_repetition_state == first.spaced_repetition_state


def test_failed_independent_retrieval_updates_failure_without_mastery_change():
    scheduler = FsrsSpacedRetrievalScheduler()
    before = ConceptMastery(
        concept_id="electrochemical-gradient",
        mastery_level=MasteryLevel.M2,
        historical_peak_mastery=MasteryLevel.M4,
    )

    after = scheduler.apply(
        mastery=before,
        event=retrieval_event(rating="again"),
    )

    assert after.retrieval_successes == 0
    assert after.retrieval_failures == 1
    assert after.mastery_level == MasteryLevel.M2
    assert after.historical_peak_mastery == MasteryLevel.M4
    assert after.next_review is not None


def test_hinted_or_recognition_attempts_cannot_drive_scheduler():
    scheduler = FsrsSpacedRetrievalScheduler()
    mastery = ConceptMastery(concept_id="electrochemical-gradient")

    with pytest.raises(ValueError, match="Hinted"):
        scheduler.apply(
            mastery=mastery,
            event=retrieval_event(hint_level=1),
        )

    with pytest.raises(ValueError, match="Recognition"):
        scheduler.apply(
            mastery=mastery,
            event=retrieval_event(evidence_kind="recognition"),
        )


def test_scheduler_requires_explicit_independence_and_rating():
    scheduler = FsrsSpacedRetrievalScheduler()
    mastery = ConceptMastery(concept_id="electrochemical-gradient")

    with pytest.raises(ValueError, match="retrieval_independent"):
        scheduler.apply(
            mastery=mastery,
            event=retrieval_event(independent=False),
        )

    event = retrieval_event()
    event.metadata.pop("retrieval_rating")
    with pytest.raises(ValueError, match="retrieval_rating"):
        scheduler.apply(mastery=mastery, event=event)


def test_out_of_order_event_fails_closed():
    scheduler = FsrsSpacedRetrievalScheduler()
    first = scheduler.apply(
        mastery=ConceptMastery(concept_id="electrochemical-gradient"),
        event=retrieval_event(),
    )

    older = retrieval_event(
        event_id="retrieval-older",
        created_at=NOW - timedelta(minutes=1),
    )
    with pytest.raises(ValueError, match="chronological"):
        scheduler.apply(mastery=first, event=older)
