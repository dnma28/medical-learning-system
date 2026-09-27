from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .learning.router import AdaptiveAction, RoutingDecision


class DeepTutorCapability(str, Enum):
    GUIDED_LEARNING = "guided_learning"
    READING_QUIZ = "reading_quiz"
    MLS_NATIVE = "mls_native"


class DeepTutorTask(BaseModel):
    capability: DeepTutorCapability
    routing_action: AdaptiveAction
    source_context: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    may_write_learner_state: bool = False
    may_write_medical_truth: bool = False
    automatic_mastery_credit: bool = False
    evidence_ceiling: str | None = None


class DeepTutorHoc90Adapter:
    """Map an MLS routing decision to a bounded DeepTutor teaching task.

    DeepTutor is used only where its upstream capability preserves MLS source
    grounding and pedagogy. High-stakes routing, active recall, error closure,
    transfer judgments, source recovery, and current-clinical verification stay
    MLS-native.
    """

    def build_task(
        self,
        decision: RoutingDecision,
        *,
        source_context: list[str] | None = None,
    ) -> DeepTutorTask:
        capability = self._capability_for(decision.action)
        return DeepTutorTask(
            capability=capability,
            routing_action=decision.action,
            source_context=list(source_context or []),
            concept_ids=list(decision.target_ids),
            instructions=[
                "Use only the source context supplied by MLS for medical claims.",
                "Do not assign mastery, close errors, or mutate learner state.",
                "Do not invent source locators, citations, or current clinical standards.",
                "Return control to the MLS Router after this bounded interaction.",
            ],
        )

    def build_reading_quiz(
        self,
        decision: RoutingDecision,
        *,
        source_context: list[str],
    ) -> DeepTutorTask:
        """Create an explicitly low-stakes, source-grounded comprehension quiz.

        Upstream ReadingQuizExtension is multiple-choice, so it is recognition
        evidence only. It must never substitute for HỌC90 free-recall evidence.
        """
        return DeepTutorTask(
            capability=DeepTutorCapability.READING_QUIZ,
            routing_action=decision.action,
            source_context=list(source_context),
            concept_ids=list(decision.target_ids),
            instructions=[
                "Generate questions only from the MLS-verified passage.",
                "Treat answers as recognition evidence only.",
                "Do not promote mastery beyond M1 from this quiz.",
            ],
            evidence_ceiling="M1",
        )

    @staticmethod
    def _capability_for(action: AdaptiveAction) -> DeepTutorCapability:
        if action in {
            AdaptiveAction.CONTINUE_SOURCE_SPINE,
            AdaptiveAction.REFERENCE_COVERAGE,
            AdaptiveAction.CROSS_BOOK_EXPANSION,
            AdaptiveAction.PREREQUISITE_REPAIR,
        }:
            return DeepTutorCapability.GUIDED_LEARNING

        # These actions require MLS-native semantics or authority:
        # - START_RETRIEVAL must remain free recall, not MCQ recognition.
        # - ERROR_REMEDIATION requires observed-error state and closure rules.
        # - TRANSFER requires an MLS mastery-evidence rubric.
        # - SOURCE_RECOVERY and VERIFY_CURRENT_EVIDENCE are evidence gates.
        return DeepTutorCapability.MLS_NATIVE
