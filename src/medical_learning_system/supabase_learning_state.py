from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .hoc90.blueprint import BlueprintStatus, Hoc90Blueprint
from .hoc90.session import Hoc90Session, LearningEvent, SessionStatus, SourceSpineRef
from .student.models import ConceptMastery, LearnerError
from .student.spaced_retrieval import FsrsSpacedRetrievalScheduler
from .student.skills import SkillNode, SkillState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    SKILL_NODES = "mls_skill_nodes"
    SKILL_STATE = "mls_skill_state"

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

    def commit_deeptutor_submission(
        self,
        *,
        event: LearningEvent,
        resumed_session: Hoc90Session,
        interaction_id: str,
    ) -> LearningEvent:
        checkpoint = (
            resumed_session.checkpoint.model_dump(mode="json")
            if resumed_session.checkpoint is not None
            else None
        )
        event_row = {
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
        response = self.client.rpc(
            "mls_commit_deeptutor_submission",
            {
                "p_session_id": event.session_id,
                "p_interaction_id": interaction_id,
                "p_event": event_row,
                "p_resumed_checkpoint": checkpoint,
                "p_updated_at": _iso(resumed_session.updated_at),
            },
        ).execute()
        result = getattr(response, "data", None)
        if not isinstance(result, dict) or not result.get("event_id"):
            raise RuntimeError("DeepTutor submission RPC readback missing")
        if str(result["event_id"]) != event.event_id:
            raise RuntimeError("DeepTutor idempotency returned a different event_id")
        if not isinstance(result.get("event"), dict):
            raise RuntimeError("DeepTutor canonical event readback missing")
        persisted = self._event_from_row(result["event"])
        if (
            persisted.event_id != event.event_id
            or persisted.session_id != event.session_id
            or persisted.metadata.get("deeptutor_interaction_id") != interaction_id
        ):
            raise RuntimeError("DeepTutor canonical event identity mismatch")
        return persisted

    @staticmethod
    def _event_from_row(stored: dict[str, Any]) -> LearningEvent:
        row = dict(stored)
        row["metadata"] = dict(row.get("metadata") or {})
        row["source_ref"] = row["metadata"].pop("source_ref", None)
        return LearningEvent.model_validate(row)

    def get_deeptutor_submission(
        self, *, session_id: str, interaction_id: str
    ) -> LearningEvent | None:
        rows = _data(
            self.client.table(self.EVENTS).select("*")
            .eq("session_id", session_id)
            .eq("metadata->>deeptutor_interaction_id", interaction_id)
            .limit(1).execute()
        )
        return self._event_from_row(rows[0]) if rows else None

    def _save_projection(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        response = self.client.rpc(
            "mls_save_learner_projection", {"p_table": table, "p_row": row}
        ).execute()
        result = getattr(response, "data", None)
        if not isinstance(result, dict):
            raise RuntimeError("Learner projection RPC readback missing")
        return dict(result)

    def load_resumable_session(self) -> Hoc90Session | None:
        active = self._latest_session(SessionStatus.ACTIVE)
        if active is not None:
            return active
        return self._latest_session(SessionStatus.PAUSED)

    def get_session(self, session_id: str) -> Hoc90Session | None:
        response = (
            self.client.table(self.SESSIONS)
            .select("*")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return Hoc90Session.model_validate(rows[0]) if rows else None

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

    def upsert_mastery(
        self,
        mastery: ConceptMastery,
        *,
        evidence_event_id: str,
    ) -> ConceptMastery:
        if not evidence_event_id:
            raise ValueError("mastery projection requires evidence_event_id")
        row = {
            "last_learning_event_id": evidence_event_id,
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
            "spaced_repetition_state": mastery.spaced_repetition_state,
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
        saved = self._save_projection(self.MASTERY, row)
        saved["state"] = saved.pop("coarse_state")
        return ConceptMastery.model_validate(saved)

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

    def apply_spaced_retrieval_event(
        self,
        event: LearningEvent,
        *,
        scheduler: FsrsSpacedRetrievalScheduler | None = None,
    ) -> ConceptMastery:
        """Project one persisted retrieval event into delayed-review timing.

        The append-only event remains the evidence source. This projection is
        replay-safe and does not promote or demote M0-M7.
        """
        if event.concept_id is None:
            raise ValueError("Retrieval events require concept_id.")

        current = self.get_mastery(event.concept_id) or ConceptMastery(
            concept_id=event.concept_id
        )
        engine = scheduler or FsrsSpacedRetrievalScheduler()
        updated = engine.apply(mastery=current, event=event)
        return self.upsert_mastery(updated, evidence_event_id=event.event_id)

    def list_due_retrieval_concept_ids(
        self,
        *,
        as_of: datetime | None = None,
        limit: int = 20,
    ) -> list[str]:
        """Return concept IDs whose delayed retrieval is due, oldest first."""
        if limit < 1:
            raise ValueError("limit must be positive")

        cutoff = as_of or _utcnow()
        response = (
            self.client.table(self.MASTERY)
            .select("concept_id,next_review")
            .lte("next_review", _iso(cutoff))
            .order("next_review")
            .limit(limit)
            .execute()
        )
        return [
            str(row["concept_id"])
            for row in _data(response)
            if row.get("concept_id") is not None
        ]

    def upsert_error(
        self,
        error: LearnerError,
        *,
        evidence_event_id: str,
    ) -> LearnerError:
        if not evidence_event_id:
            raise ValueError("learner-error projection requires evidence_event_id")
        row = {
            "last_learning_event_id": evidence_event_id,
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


    def upsert_skill_node(self, node: SkillNode) -> SkillNode:
        row = {
            "skill_node_id": node.skill_node_id,
            "vi_name": node.vi_name,
            "english_alias": node.english_alias,
            "domain": node.domain,
            "parent_ids": node.parent_ids,
            "required_prerequisites": node.required_prerequisites,
            "supporting_prerequisites": node.supporting_prerequisites,
            "unlock_rule": node.unlock_rule,
            "updated_at": _iso(node.updated_at),
        }
        (
            self.client.table(self.SKILL_NODES)
            .upsert(row, on_conflict="skill_node_id")
            .execute()
        )
        return node

    def get_skill_node(self, skill_node_id: str) -> SkillNode | None:
        response = (
            self.client.table(self.SKILL_NODES)
            .select("*")
            .eq("skill_node_id", skill_node_id)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return SkillNode.model_validate(rows[0]) if rows else None

    def upsert_skill_state(
        self,
        state: SkillState,
        *,
        evidence_event_id: str,
    ) -> SkillState:
        if not evidence_event_id:
            raise ValueError("skill-state projection requires evidence_event_id")
        row = {
            "last_learning_event_id": evidence_event_id,
            "skill_node_id": state.skill_node_id,
            "mastery_level": state.mastery_level.value,
            "current_strength": state.current_strength,
            "forgetting_risk": state.forgetting_risk,
            "open_error_ids": state.open_error_ids,
            "last_test": _iso(state.last_test),
            "next_review": _iso(state.next_review),
            "evidence_summary": state.evidence_summary,
            "updated_at": _iso(state.updated_at),
        }
        return SkillState.model_validate(self._save_projection(self.SKILL_STATE, row))

    def get_skill_state(self, skill_node_id: str) -> SkillState | None:
        response = (
            self.client.table(self.SKILL_STATE)
            .select("*")
            .eq("skill_node_id", skill_node_id)
            .limit(1)
            .execute()
        )
        rows = _data(response)
        return SkillState.model_validate(rows[0]) if rows else None

    def save_blueprint(self, blueprint: Hoc90Blueprint) -> Hoc90Blueprint:
        source_spine = [
            ref.model_dump(mode="json")
            for ref in blueprint.source_spine
        ]
        response = self.client.rpc(
            "mls_save_hoc90_blueprint",
            {
                "p_lesson_id": blueprint.lesson_id,
                "p_status": blueprint.status.value,
                "p_curriculum_position": blueprint.curriculum_position,
                "p_source_spine": source_spine,
                "p_payload": blueprint.model_dump(mode="json"),
                "p_updated_at": _iso(_utcnow()),
            },
        ).execute()
        if not isinstance(getattr(response, "data", None), dict):
            raise RuntimeError("HOC90 blueprint RPC readback missing")
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
