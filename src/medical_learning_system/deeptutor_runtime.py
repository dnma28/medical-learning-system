from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from hashlib import sha256
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .deeptutor_adapter import DeepTutorCapability, DeepTutorTask
from .hoc90.session import LearningEvent, LearningEventType, SourceSpineRef


class DeepTutorRuntimeUnavailable(RuntimeError):
    pass


class DeepTutorReadingInput(BaseModel):
    material_id: str = Field(min_length=1)
    locator: int = Field(default=1, ge=1)
    source_anchor: str = Field(default="", max_length=4096)
    locale: str = Field(default="vi", max_length=32)
    selection: str = Field(default="", max_length=10_000)


class DeepTutorExecutionResult(BaseModel):
    interaction_id: str = Field(default_factory=lambda: str(uuid4()))
    capability: DeepTutorCapability
    result_type: str
    title: str = ""
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    source_sha256: str
    authoritative: bool = False
    evidence_ceiling: str | None = None
    private_evaluation: dict[str, Any] = Field(default_factory=dict, exclude=True)


Runner = Callable[
    [DeepTutorTask, DeepTutorReadingInput, str],
    Awaitable[dict[str, Any]],
]


class DeepTutorRuntimeExecutor:
    """Execute the safe DeepTutor subset against MLS-provided source text.

    The executor never writes Supabase state. It returns learner-facing output
    plus a private evaluator payload. MLS decides whether and how a later
    learner response becomes an append-only LearningEvent.
    """

    def __init__(self, runner: Runner | None = None):
        self._runner = runner

    async def execute(
        self,
        task: DeepTutorTask,
        *,
        reading: DeepTutorReadingInput,
    ) -> DeepTutorExecutionResult:
        if task.capability == DeepTutorCapability.MLS_NATIVE:
            raise ValueError(
                "This HỌC90 action is intentionally MLS-native and must not be "
                "delegated to DeepTutor."
            )

        source_text = self._source_text(task)
        self._validate_source_bounds(task.capability, source_text, reading.selection)

        raw = (
            await self._runner(task, reading, source_text)
            if self._runner is not None
            else await self._run_upstream(task, reading, source_text)
        )
        return self._normalize_result(task, source_text, raw)

    @staticmethod
    def _source_text(task: DeepTutorTask) -> str:
        parts = [part.strip() for part in task.source_context if part.strip()]
        if not parts:
            raise ValueError("DeepTutor execution requires MLS-verified source context.")
        return "\n\n--- MLS SOURCE SEGMENT ---\n\n".join(parts)

    @staticmethod
    def _validate_source_bounds(
        capability: DeepTutorCapability,
        source_text: str,
        selection: str,
    ) -> None:
        if len(source_text) > 60_000:
            raise ValueError(
                "DeepTutor reading context exceeds 60,000 characters; MLS must "
                "supply a smaller source-grounded unit."
            )
        if capability == DeepTutorCapability.GUIDED_LEARNING:
            selected = selection.strip() or source_text
            if len(selected) > 10_000:
                raise ValueError(
                    "Guided Learning selection exceeds 10,000 characters; MLS "
                    "must supply a bounded subsection or passage."
                )

    async def _run_upstream(
        self,
        task: DeepTutorTask,
        reading: DeepTutorReadingInput,
        source_text: str,
    ) -> dict[str, Any]:
        try:
            from deeptutor.reading.extensions import ReadingContext
            from deeptutor.reading.quiz import ReadingQuizExtension
            from deeptutor.reading.study_guidance import StudyGuidanceExtension
        except ImportError as exc:
            raise DeepTutorRuntimeUnavailable(
                "DeepTutor is not installed. Install the optional 'deeptutor' "
                "extra in a Python 3.11+ environment."
            ) from exc

        selection = reading.selection.strip()
        if task.capability == DeepTutorCapability.GUIDED_LEARNING:
            selection = selection or source_text
            extension = StudyGuidanceExtension()
            action = "guide"
        elif task.capability == DeepTutorCapability.READING_QUIZ:
            extension = ReadingQuizExtension()
            action = "start"
        else:
            raise ValueError(f"Unsupported DeepTutor capability: {task.capability}")

        context = ReadingContext(
            material_id=reading.material_id,
            locator=reading.locator,
            source_anchor=reading.source_anchor,
            locale=reading.locale,
            selection=selection,
            visible_text=source_text,
        )
        with self._provider_scope():
            result = await extension.run_action(action, context)
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        if isinstance(result, dict):
            return result
        raise TypeError("DeepTutor extension returned an unsupported result shape.")

    @staticmethod
    @contextmanager
    def _provider_scope():
        """Optionally inject an MLS-owned DeepTutor model configuration.

        If MLS_DEEPTUTOR_MODEL is absent, DeepTutor keeps using its own configured
        model catalog. When it is present, the backend can run headlessly using
        environment secrets without writing DeepTutor user settings to disk.
        """
        model = os.getenv("MLS_DEEPTUTOR_MODEL", "").strip()
        if not model:
            yield
            return

        api_key = (
            os.getenv("MLS_DEEPTUTOR_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        if not api_key:
            raise DeepTutorRuntimeUnavailable(
                "MLS_DEEPTUTOR_MODEL is configured but no MLS_DEEPTUTOR_API_KEY "
                "or OPENAI_API_KEY is available."
            )

        try:
            from deeptutor.services.llm.config import (
                LLMConfig,
                reset_scoped_llm_config,
                set_scoped_llm_config,
            )
        except ImportError as exc:
            raise DeepTutorRuntimeUnavailable(
                "DeepTutor provider configuration is unavailable."
            ) from exc

        binding = os.getenv("MLS_DEEPTUTOR_BINDING", "openai").strip() or "openai"
        provider = (
            os.getenv("MLS_DEEPTUTOR_PROVIDER", binding).strip() or binding
        )
        base_url = (
            os.getenv("MLS_DEEPTUTOR_BASE_URL", "").strip()
            or ("https://api.openai.com/v1" if binding == "openai" else None)
        )
        config = LLMConfig(
            model=model,
            api_key=api_key,
            base_url=base_url,
            effective_url=base_url,
            binding=binding,
            provider_name=provider,
            api_format=os.getenv("MLS_DEEPTUTOR_API_FORMAT", "auto").strip() or "auto",
            wire_api="auto",
        )
        token = set_scoped_llm_config(config)
        try:
            yield
        finally:
            reset_scoped_llm_config(token)

    @staticmethod
    def _normalize_result(
        task: DeepTutorTask,
        source_text: str,
        raw: dict[str, Any],
    ) -> DeepTutorExecutionResult:
        payload = dict(raw.get("payload") or {})
        private_evaluation: dict[str, Any] = {}

        if task.capability == DeepTutorCapability.READING_QUIZ:
            public_questions: list[dict[str, Any]] = []
            answer_key: dict[str, int] = {}
            for row in payload.get("questions") or []:
                if not isinstance(row, dict):
                    continue
                qid = str(row.get("id") or "").strip()
                prompt = str(row.get("prompt") or "").strip()
                choices = row.get("choices")
                correct = row.get("correct_choice_index")
                if not qid or not prompt or not isinstance(choices, list):
                    continue
                public_questions.append(
                    {"id": qid, "prompt": prompt, "choices": list(choices)}
                )
                if isinstance(correct, int):
                    answer_key[qid] = correct
            payload = {**payload, "questions": public_questions}
            private_evaluation["answer_key"] = answer_key

        return DeepTutorExecutionResult(
            capability=task.capability,
            result_type=str(raw.get("type") or ""),
            title=str(raw.get("title") or ""),
            message=str(raw.get("message") or ""),
            payload=payload,
            source_sha256=sha256(source_text.encode("utf-8")).hexdigest(),
            evidence_ceiling=task.evidence_ceiling,
            private_evaluation=private_evaluation,
        )

    @staticmethod
    def build_response_event_candidate(
        *,
        session_id: str,
        task: DeepTutorTask,
        execution: DeepTutorExecutionResult,
        learner_response: str,
        question_id: str | None = None,
        concept_id: str | None = None,
        source_ref: SourceSpineRef | None = None,
        hint_level: int = 0,
    ) -> LearningEvent:
        response = learner_response.strip()
        if not response:
            raise ValueError("A learner response is required before recording evidence.")

        event_type = (
            LearningEventType.RETRIEVAL
            if task.routing_action.value == "start_retrieval"
            else LearningEventType.SOCRATIC_RESPONSE
        )
        return LearningEvent(
            session_id=session_id,
            event_type=event_type,
            concept_id=concept_id or (task.concept_ids[0] if task.concept_ids else None),
            question_id=question_id,
            source_ref=source_ref,
            answer_summary=response,
            hint_level=hint_level,
            metadata={
                "deeptutor_interaction_id": execution.interaction_id,
                "deeptutor_capability": execution.capability.value,
                "source_sha256": execution.source_sha256,
                "automatic_mastery_credit": False,
                "evidence_ceiling": execution.evidence_ceiling,
            },
        )

    @staticmethod
    def build_quiz_answer_event_candidate(
        *,
        session_id: str,
        task: DeepTutorTask,
        execution: DeepTutorExecutionResult,
        question_id: str,
        selected_choice_index: int,
        concept_id: str | None = None,
        source_ref: SourceSpineRef | None = None,
    ) -> LearningEvent:
        answer_key = execution.private_evaluation.get("answer_key") or {}
        if question_id not in answer_key:
            raise ValueError("Unknown or non-evaluable DeepTutor quiz question.")
        correct = selected_choice_index == answer_key[question_id]

        return LearningEvent(
            session_id=session_id,
            event_type=LearningEventType.SOCRATIC_RESPONSE,
            concept_id=concept_id or (task.concept_ids[0] if task.concept_ids else None),
            question_id=question_id,
            source_ref=source_ref,
            outcome="correct" if correct else "incorrect",
            answer_summary=f"selected_choice_index={selected_choice_index}",
            metadata={
                "deeptutor_interaction_id": execution.interaction_id,
                "deeptutor_capability": execution.capability.value,
                "source_sha256": execution.source_sha256,
                "evidence_kind": "recognition",
                "automatic_mastery_credit": False,
                "evidence_ceiling": "M1",
            },
        )
