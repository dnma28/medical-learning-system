from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .learning.router import AdaptiveAction, RoutingDecision


class DeepTutorCapability(str, Enum):
    GUIDED_LEARNING = "guided_learning"
    DEEP_QUESTION = "deep_question"
    AGENT_LOOP = "agent_loop"


class DeepTutorTask(BaseModel):
    capability: DeepTutorCapability
    source_context: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    may_write_learner_state: bool = False
    may_write_medical_truth: bool = False


class DeepTutorHoc90Adapter:
    """Map an MLS routing decision to a bounded DeepTutor teaching task.

    MLS remains authoritative for source selection, routing, learner evidence,
    mastery, errors, checkpoints, and medical truth. DeepTutor may generate a
    teaching interaction, but its output is evidence/input to MLS rather than
    an authoritative state transition.
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
            source_context=list(source_context or []),
            concept_ids=list(decision.target_ids),
            instructions=[
                "Use only the source context supplied by MLS for medical claims.",
                "Ask the learner to answer before revealing explanations or corrections.",
                "Return learner-facing content only; do not assign mastery or mutate learner state.",
                "Do not invent source locators, citations, or current clinical standards.",
                "Return control to the MLS source spine after bounded remediation or expansion.",
            ],
        )

    @staticmethod
    def _capability_for(action: AdaptiveAction) -> DeepTutorCapability:
        if action in {
            AdaptiveAction.START_RETRIEVAL,
            AdaptiveAction.ERROR_REMEDIATION,
            AdaptiveAction.PREREQUISITE_REPAIR,
            AdaptiveAction.TRANSFER,
        }:
            return DeepTutorCapability.DEEP_QUESTION
        if action in {
            AdaptiveAction.CONTINUE_SOURCE_SPINE,
            AdaptiveAction.REFERENCE_COVERAGE,
            AdaptiveAction.CROSS_BOOK_EXPANSION,
        }:
            return DeepTutorCapability.GUIDED_LEARNING
        # Source recovery and current-evidence verification are MLS-controlled
        # operations. DeepTutor can assist only after MLS has resolved evidence.
        return DeepTutorCapability.AGENT_LOOP
