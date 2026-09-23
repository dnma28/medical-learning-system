from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .hoc90.blueprint import BlueprintStatus, Hoc90Blueprint
from .hoc90.session import Hoc90Session, LearningEvent, SessionStatus, SourceSpineRef
from .student.models import ConceptMastery, LearnerError


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _data(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


class SupabaseLearningStateStore:
    """Backend-only persistence for adaptive HỌC90 state.

    This store persists learner/runtime state only. It must never promote
    learner state into canonical medical knowledge.
    """

    SESSIONS = "mls_learning_sessions"
    EVENTS = "mls_learning_events"
    MASTERY = "mls_concept_mastery"
    ERRORS = "mls_learner_errors"
    BLUEPRINTS = "mls_hoc90_blueprints"

    def __init__(self, client: Any):
        self.client = client

    def save_session(self, session: Hoc90Session) -> Hoc90Session:
        row = {
            "session_id": session.session_id,
            "topic": session.topic,
            "target_outcome": session.target_outcome,
            "status": session.status.value,
            "curriculum_position": session.curriculum_position,
            "source_spine": [
                item.model_dump(mode="json")
                if isinstance(item, SourceSpineRef)
                else item
                for item in session.source_spine
            ],
            "toc_position": session.toc_position,
            "checkpoint": (
                session.checkpoint.model_dump(mode="json")
                if session.checkpoint is not None
                else None
            ),
            "stages": [stage.model_dump(mode="json") for stage in session.stages],
            "started_at": _iso(session.started_at),
            "completed_at": _iso(session.completed_at),
            "updated_at": _iso(session.updated_at),
        }
        (
            self.client.table(self.SESSIONS)
            .upsert(row, on_conflict="session_id")
            .execute()
        )
        return session

    def load_resumable_session(self) -> Hoc90Session | None:
        active = self._latest_session(SessionStatus.ACTIVE)
        if active is not None:
            return active
        return self._latest_session(SessionStatus.PAUSED)

    def _latest_session(self, status: SessionStatus) -> Hoc90Session | None:
        response = (
            self.client.table(self.SESSIONS)
            .select("*")
            .eq("status", status.value)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return Hoc90Session.model_validate(rows[0]) if rows else None

    def append_event(self, event: LearningEvent) -> LearningEvent:
        row = {
            "event_id": event.event_id,
            "session_id": event.session_id,
            "event_type": event.event_type.value,
            "concept_id": event.concept_id,
            "question_id": event.question_id,
            "outcome": event.outcome,
            "answer_summary": event.answer_summary,
            "hint_level": event.hint_level,
            "metadata": {
                **event.metadata,
                **(
                    {"source_ref": event.source_ref.model_dump(mode="json")}
                    if event.source_ref is not None
                    else {}
                ),
            },
            "created_at": _iso(event.created_at),
        }
        # Learning events are append-only: a duplicate event ID is an error,
        # not an update.
        self.client.table(self.EVENTS).insert(row).execute()
        return event

    def upsert_mastery(self, mastery: ConceptMastery) -> ConceptMastery:
        row = {
            "concept_id": mastery.concept_id,
            "coarse_state": mastery.state.value,
            "mastery_level": mastery.mastery_level.value,
            "historical_peak_mastery": mastery.historical_peak_mastery.value,
            "current_strength": mastery.current_strength,
            "retrieval_successes": mastery.retrieval_successes,
            "retrieval_failures": mastery.retrieval_failures,
            "last_exposure": _iso(mastery.last_exposure),
            "last_independent_retrieval": _iso(
                mastery.last_independent_retrieval
            ),
            "next_review": _iso(mastery.next_review),
            "mechanism_explained_independently": (
                mastery.mechanism_explained_independently
            ),
            "feynman_pass": mastery.feynman_pass,
            "counterfactual_pass": mastery.counterfactual_pass,
            "transfer_pass": mastery.transfer_pass,
            "clinical_transfer_pass": mastery.clinical_transfer_pass,
            "integration_pass": mastery.integration_pass,
            "open_error_ids": mastery.open_error_ids,
            "evidence_for_mastery": mastery.evidence_for_mastery,
            "source_contexts_seen": mastery.source_contexts_seen,
            "updated_at": _iso(mastery.updated_at),
        }
        (
            self.client.table(self.MASTERY)
            .upsert(row, on_conflict="concept_id")
            .execute()
        )
        return mastery

    def get_mastery(self, concept_id: str) -> ConceptMastery | None:
        response = (
            self.client.table(self.MASTERY)
            .select("*")
            .eq("concept_id", concept_id)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        if not rows:
            return None
        row = dict(rows[0])
        row["state"] = row.pop("coarse_state")
        return ConceptMastery.model_validate(row)

    def upsert_error(self, error: LearnerError) -> LearnerError:
        row = {
            "error_id": error.id,
            "concept_id": error.concept_id,
            "observed_statement": error.statement,
            "error_type": error.error_type.value,
            "status": error.status.value,
            "correction": error.correction,
            "underlying_gap": error.underlying_gap,
            "contexts": error.contexts,
            "hint_response": error.hint_response,
            "next_probe": error.next_probe,
            "times_seen": error.times_seen,
            "first_seen": _iso(error.first_seen),
            "last_seen": _iso(error.last_seen),
            "updated_at": _iso(error.updated_at),
        }
        (
            self.client.table(self.ERRORS)
            .upsert(row, on_conflict="error_id")
            .execute()
        )
        return error

    def list_open_errors(self, *, concept_id: str | None = None) -> list[LearnerError]:
        query = (
            self.client.table(self.ERRORS)
            .select("*")
            .in_("status", ["open", "self_corrected", "retest_required", "corrected"])
        )
        if concept_id is not None:
            query = query.eq("concept_id", concept_id)
        response = query.order("last_seen", desc=True).execute()

        errors: list[LearnerError] = []
        for stored in _data(response):
            row = dict(stored)
            row["id"] = row.pop("error_id")
            row["statement"] = row.pop("observed_statement")
            errors.append(LearnerError.model_validate(row))
        return errors


    def save_blueprint(self, blueprint: Hoc90Blueprint) -> Hoc90Blueprint:
        if blueprint.status == BlueprintStatus.ACTIVE:
            (
                self.client.table(self.BLUEPRINTS)
                .update({"status": BlueprintStatus.SUPERSEDED.value})
                .eq("status", BlueprintStatus.ACTIVE.value)
                .execute()
            )

        row = {
            "lesson_id": blueprint.lesson_id,
            "status": blueprint.status.value,
            "curriculum_position": blueprint.curriculum_position,
            "source_spine": [
                ref.model_dump(mode="json")
                for ref in blueprint.source_spine
            ],
            "payload": blueprint.model_dump(mode="json"),
            "updated_at": _iso(_utcnow()),
        }
        (
            self.client.table(self.BLUEPRINTS)
            .upsert(row, on_conflict="lesson_id")
            .execute()
        )
        return blueprint

    def get_active_blueprint(self) -> Hoc90Blueprint | None:
        response = (
            self.client.table(self.BLUEPRINTS)
            .select("*")
            .eq("status", BlueprintStatus.ACTIVE.value)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        if not rows:
            return None
        return Hoc90Blueprint.model_validate(rows[0]["payload"])
