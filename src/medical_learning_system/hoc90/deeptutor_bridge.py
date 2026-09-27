from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from ..deeptutor_adapter import DeepTutorHoc90Adapter, DeepTutorTask
from ..deeptutor_runtime import (
    DeepTutorExecutionResult,
    DeepTutorReadingInput,
    DeepTutorRuntimeExecutor,
)
from ..learning.router import RoutingDecision
from .session import Hoc90Session, LearningEvent, SessionCheckpoint, SourceSpineRef


class LearningStateStore(Protocol):
    def get_session(self, session_id: str) -> Hoc90Session | None: ...
    def save_session(self, session: Hoc90Session) -> Hoc90Session: ...
    def append_event(self, event: LearningEvent) -> LearningEvent: ...


class DeepTutorSubmission(BaseModel):
    interaction_id: str = Field(min_length=1)
    learner_response: str | None = None
    question_id: str | None = None
    selected_choice_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_shape(self) -> "DeepTutorSubmission":
        has_text = bool((self.learner_response or "").strip())
        has_choice = self.question_id is not None and self.selected_choice_index is not None
        if has_text == has_choice:
            raise ValueError(
                "Provide either learner_response or question_id + selected_choice_index."
            )
        return self


class PreparedDeepTutorInteraction(BaseModel):
    session_id: str
    interaction: DeepTutorExecutionResult


class Hoc90DeepTutorBridge:
    """Persist the boundary between a DeepTutor turn and MLS learner evidence.

    Preparing an interaction pauses the HỌC90 session with a backend-only
    pending checkpoint. Submitting a response verifies that checkpoint, appends
    exactly one MLS learning event, clears the pending interaction, and resumes
    the session. No mastery state is changed here.
    """

    def __init__(
        self,
        *,
        store: LearningStateStore,
        executor: DeepTutorRuntimeExecutor | None = None,
        adapter: DeepTutorHoc90Adapter | None = None,
    ):
        self.store = store
        self.executor = executor or DeepTutorRuntimeExecutor()
        self.adapter = adapter or DeepTutorHoc90Adapter()

    async def prepare(
        self,
        *,
        session_id: str,
        decision: RoutingDecision,
        source_context: list[str],
        reading: DeepTutorReadingInput,
        source_ref: SourceSpineRef | None = None,
        quiz: bool = False,
    ) -> PreparedDeepTutorInteraction:
        session = self._require_session(session_id)
        if (
            session.checkpoint is not None
            and session.checkpoint.pending_deeptutor_interaction is not None
        ):
            raise RuntimeError(
                "The HỌC90 session already has a pending DeepTutor interaction."
            )

        resolved_source_ref = source_ref or session.primary_source_ref()
        if resolved_source_ref is None:
            raise ValueError("A structured HỌC90 source_ref is required.")

        task = (
            self.adapter.build_reading_quiz(decision, source_context=source_context)
            if quiz
            else self.adapter.build_task(decision, source_context=source_context)
        )
        execution = await self.executor.execute(task, reading=reading)

        current = session.checkpoint
        checkpoint = SessionCheckpoint(
            concept_id=(
                task.concept_ids[0]
                if task.concept_ids
                else (current.concept_id if current else None)
            ),
            question_id=current.question_id if current else None,
            hint_level=current.hint_level if current else 0,
            toc_position=session.toc_position,
            source_ref=resolved_source_ref,
            current_branch=current.current_branch if current else None,
            return_to_source=current.return_to_source if current else None,
            working_mastery_delta=(
                dict(current.working_mastery_delta) if current else {}
            ),
            open_error_ids=list(current.open_error_ids) if current else [],
            pending_deeptutor_interaction=self._pending_payload(task, execution),
        )

        if session.status.value == "planned":
            session = session.start()
        self.store.save_session(session.pause(checkpoint))
        return PreparedDeepTutorInteraction(
            session_id=session_id,
            interaction=execution,
        )

    def submit(
        self,
        *,
        session_id: str,
        submission: DeepTutorSubmission,
    ) -> LearningEvent:
        session = self._require_session(session_id)
        checkpoint = session.checkpoint
        if checkpoint is None or checkpoint.pending_deeptutor_interaction is None:
            raise RuntimeError("The HỌC90 session has no pending DeepTutor interaction.")

        pending = dict(checkpoint.pending_deeptutor_interaction)
        if pending.get("interaction_id") != submission.interaction_id:
            raise RuntimeError("DeepTutor interaction_id does not match the pending checkpoint.")

        task = DeepTutorTask.model_validate(pending["task"])
        execution_payload = dict(pending["execution"])
        execution_payload["private_evaluation"] = dict(
            pending.get("private_evaluation") or {}
        )
        execution = DeepTutorExecutionResult.model_validate(execution_payload)

        if submission.learner_response is not None:
            event = self.executor.build_response_event_candidate(
                session_id=session_id,
                task=task,
                execution=execution,
                learner_response=submission.learner_response,
                question_id=submission.question_id,
                concept_id=checkpoint.concept_id,
                source_ref=checkpoint.source_ref,
                hint_level=checkpoint.hint_level,
            )
        else:
            event = self.executor.build_quiz_answer_event_candidate(
                session_id=session_id,
                task=task,
                execution=execution,
                question_id=str(submission.question_id),
                selected_choice_index=int(submission.selected_choice_index),
                concept_id=checkpoint.concept_id,
                source_ref=checkpoint.source_ref,
            )

        self.store.append_event(event)

        cleared = checkpoint.model_copy(
            update={"pending_deeptutor_interaction": None}
        )
        resumed = session.model_copy(update={"checkpoint": cleared}).resume()
        self.store.save_session(resumed)
        return event

    def _require_session(self, session_id: str) -> Hoc90Session:
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown HỌC90 session: {session_id}")
        return session

    @staticmethod
    def _pending_payload(
        task: DeepTutorTask,
        execution: DeepTutorExecutionResult,
    ) -> dict[str, Any]:
        public_execution = execution.model_dump(mode="json")
        return {
            "interaction_id": execution.interaction_id,
            "task": task.model_dump(mode="json"),
            "execution": public_execution,
            "private_evaluation": dict(execution.private_evaluation),
        }
