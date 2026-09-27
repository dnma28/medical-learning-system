from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..hoc90.session import LearningEvent, LearningEventType
from .models import ConceptMastery

FSRS_ENGINE_VERSION = "6.3.2"
DEFAULT_DESIRED_RETENTION = 0.9
DEFAULT_MAXIMUM_INTERVAL_DAYS = 36500


class RetrievalRating(str, Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class SpacedRetrievalState(BaseModel):
    """Persisted, replay-safe state for one concept's spaced-retrieval card."""

    engine: Literal["fsrs"] = "fsrs"
    engine_version: str = FSRS_ENGINE_VERSION
    desired_retention: float = Field(
        default=DEFAULT_DESIRED_RETENTION, gt=0.0, lt=1.0
    )
    learning_steps_seconds: list[int] = Field(default_factory=list)
    relearning_steps_seconds: list[int] = Field(default_factory=list)
    maximum_interval_days: int = Field(
        default=DEFAULT_MAXIMUM_INTERVAL_DAYS, ge=1
    )
    fuzzing_enabled: bool = False
    card: dict[str, Any]
    last_event_id: str


class FsrsSpacedRetrievalScheduler:
    """Map explicit independent retrieval evidence to FSRS review timing.

    This component changes review timing only. It never raises or lowers M0-M7,
    closes learner errors, changes curriculum position, or writes medical truth.
    """

    def __init__(
        self,
        *,
        desired_retention: float = DEFAULT_DESIRED_RETENTION,
        learning_steps_seconds: tuple[int, ...] = (),
        relearning_steps_seconds: tuple[int, ...] = (),
        maximum_interval_days: int = DEFAULT_MAXIMUM_INTERVAL_DAYS,
    ) -> None:
        if not 0.0 < desired_retention < 1.0:
            raise ValueError("desired_retention must be between 0 and 1")
        if maximum_interval_days < 1:
            raise ValueError("maximum_interval_days must be positive")
        if any(
            step <= 0
            for step in (*learning_steps_seconds, *relearning_steps_seconds)
        ):
            raise ValueError("learning and relearning steps must be positive")

        try:
            installed_version = version("fsrs")
        except PackageNotFoundError as exc:
            raise RuntimeError(
                "FSRS is not installed. Install with: pip install -e '.[fsrs]'"
            ) from exc
        if installed_version != FSRS_ENGINE_VERSION:
            raise RuntimeError(
                "Unsupported fsrs version "
                f"{installed_version}; expected {FSRS_ENGINE_VERSION}."
            )

        from fsrs import Card, Rating, Scheduler

        self._Card = Card
        self._Rating = Rating
        self.desired_retention = desired_retention
        self.learning_steps_seconds = learning_steps_seconds
        self.relearning_steps_seconds = relearning_steps_seconds
        self.maximum_interval_days = maximum_interval_days
        self._scheduler = Scheduler(
            desired_retention=desired_retention,
            learning_steps=[
                timedelta(seconds=seconds) for seconds in learning_steps_seconds
            ],
            relearning_steps=[
                timedelta(seconds=seconds) for seconds in relearning_steps_seconds
            ],
            maximum_interval=maximum_interval_days,
            enable_fuzzing=False,
        )

    def apply(
        self,
        *,
        mastery: ConceptMastery,
        event: LearningEvent,
    ) -> ConceptMastery:
        """Apply one retrieval event to scheduling state.

        The event must already represent an independently attempted free-retrieval
        task. The caller remains responsible for persisting the append-only event.
        Re-applying the same event ID is idempotent.
        """

        rating = self._validate_event(mastery=mastery, event=event)
        review_at = _as_utc(event.created_at)

        stored = mastery.spaced_repetition_state
        if stored:
            state = SpacedRetrievalState.model_validate(stored)
            self._validate_persisted_config(state)
            if state.last_event_id == event.event_id:
                return mastery

            card = self._Card.from_dict(state.card)
            if card.last_review is not None and review_at <= card.last_review:
                raise ValueError(
                    "Retrieval events must be applied in chronological order."
                )
        else:
            card = self._Card(
                card_id=_stable_card_id(mastery.concept_id),
                due=review_at,
            )

        fsrs_rating = {
            RetrievalRating.AGAIN: self._Rating.Again,
            RetrievalRating.HARD: self._Rating.Hard,
            RetrievalRating.GOOD: self._Rating.Good,
            RetrievalRating.EASY: self._Rating.Easy,
        }[rating]

        duration = event.metadata.get("response_time_ms")
        review_duration = (
            int(duration)
            if isinstance(duration, int)
            and not isinstance(duration, bool)
            and duration >= 0
            else None
        )
        card, _review_log = self._scheduler.review_card(
            card=card,
            rating=fsrs_rating,
            review_datetime=review_at,
            review_duration=review_duration,
        )

        next_state = SpacedRetrievalState(
            desired_retention=self.desired_retention,
            learning_steps_seconds=list(self.learning_steps_seconds),
            relearning_steps_seconds=list(self.relearning_steps_seconds),
            maximum_interval_days=self.maximum_interval_days,
            fuzzing_enabled=False,
            card=card.to_dict(),
            last_event_id=event.event_id,
        )

        remembered = rating != RetrievalRating.AGAIN
        return mastery.model_copy(
            update={
                "retrieval_successes": (
                    mastery.retrieval_successes + (1 if remembered else 0)
                ),
                "retrieval_failures": (
                    mastery.retrieval_failures + (0 if remembered else 1)
                ),
                "last_exposure": review_at,
                "last_independent_retrieval": review_at,
                "next_review": card.due,
                "spaced_repetition_state": next_state.model_dump(mode="json"),
                "updated_at": review_at,
            }
        )

    def _validate_event(
        self,
        *,
        mastery: ConceptMastery,
        event: LearningEvent,
    ) -> RetrievalRating:
        if event.event_type != LearningEventType.RETRIEVAL:
            raise ValueError("FSRS scheduling accepts retrieval events only.")
        if event.concept_id is None:
            raise ValueError("Retrieval events require concept_id.")
        if event.concept_id != mastery.concept_id:
            raise ValueError("Retrieval event concept_id does not match mastery.")
        if event.hint_level != 0:
            raise ValueError(
                "Hinted attempts are not independent spaced-retrieval evidence."
            )
        if event.metadata.get("retrieval_independent") is not True:
            raise ValueError(
                "Retrieval events must explicitly set retrieval_independent=true."
            )
        if event.metadata.get("evidence_kind") == "recognition":
            raise ValueError(
                "Recognition evidence cannot drive free-retrieval scheduling."
            )

        raw_rating = event.metadata.get("retrieval_rating")
        try:
            return RetrievalRating(str(raw_rating).casefold())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in RetrievalRating)
            raise ValueError(
                f"retrieval_rating must be one of: {allowed}."
            ) from exc

    def _validate_persisted_config(self, state: SpacedRetrievalState) -> None:
        expected = (
            FSRS_ENGINE_VERSION,
            self.desired_retention,
            list(self.learning_steps_seconds),
            list(self.relearning_steps_seconds),
            self.maximum_interval_days,
            False,
        )
        actual = (
            state.engine_version,
            state.desired_retention,
            state.learning_steps_seconds,
            state.relearning_steps_seconds,
            state.maximum_interval_days,
            state.fuzzing_enabled,
        )
        if actual != expected:
            raise RuntimeError(
                "Persisted spaced-retrieval state uses a different scheduler "
                "configuration; reschedule it explicitly before continuing."
            )


def _stable_card_id(concept_id: str) -> int:
    digest = sha256(concept_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Retrieval event created_at must be timezone-aware.")
    return value.astimezone(timezone.utc)
