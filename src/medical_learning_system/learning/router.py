from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ..source_map import LearningValue


class LearningRoute(str, Enum):
    SOURCE_RETRIEVAL = "source_retrieval"
    CONCEPT_EXPLANATION = "concept_explanation"
    ACTIVE_RECALL = "active_recall"
    ERROR_REMEDIATION = "error_remediation"


class AdaptiveAction(str, Enum):
    START_RETRIEVAL = "start_retrieval"
    VERIFY_CURRENT_EVIDENCE = "verify_current_evidence"
    PREREQUISITE_REPAIR = "prerequisite_repair"
    ERROR_REMEDIATION = "error_remediation"
    SOURCE_RECOVERY = "source_recovery"
    REFERENCE_COVERAGE = "reference_coverage"
    CONTINUE_SOURCE_SPINE = "continue_source_spine"
    CROSS_BOOK_EXPANSION = "cross_book_expansion"
    TRANSFER = "transfer"


class QualityMode(str, Enum):
    FAST = "fast"
    DEEP = "deep"
    CRITICAL = "critical"


class LearningRequest(BaseModel):
    query: str
    wants_quiz: bool = False
    known_error_id: str | None = None
    needs_source_lookup: bool = True


class RoutingContext(BaseModel):
    session_start: bool = False
    source_spine: str | None = None
    current_toc_item: str | None = None
    current_learning_value: LearningValue = LearningValue.CORE_MASTERY

    due_retrieval_concept_ids: list[str] = Field(default_factory=list)
    weak_required_prerequisite_ids: list[str] = Field(default_factory=list)
    open_error_ids: list[str] = Field(default_factory=list)

    source_gap: bool = False
    source_anchor_available: bool = True
    learner_requested_reference_detail: bool = False

    freshness_required: bool = False
    freshness_verified: bool = False

    concept_is_complex: bool = False
    source_is_insufficient_for_explanation: bool = False
    ready_for_transfer: bool = False


class RoutingDecision(BaseModel):
    action: AdaptiveAction
    quality_mode: QualityMode
    reason: str
    target_ids: list[str] = Field(default_factory=list)
    return_to_source_spine: str | None = None
    requires_user_approval: bool = False


class LearningRouter:
    """Deterministic source-aware HỌC90 routing rules.

    The router may adapt bounded within-session paths. Large curriculum changes
    remain learner-approved.
    """

    def route(self, request: LearningRequest) -> LearningRoute:
        """Legacy coarse router retained for compatibility."""
        if request.known_error_id:
            return LearningRoute.ERROR_REMEDIATION
        if request.wants_quiz:
            return LearningRoute.ACTIVE_RECALL
        if request.needs_source_lookup:
            return LearningRoute.SOURCE_RETRIEVAL
        return LearningRoute.CONCEPT_EXPLANATION

    def route_next(self, context: RoutingContext) -> RoutingDecision:
        quality = self._quality_mode(context)

        if context.session_start and context.due_retrieval_concept_ids:
            return RoutingDecision(
                action=AdaptiveAction.START_RETRIEVAL,
                quality_mode=quality,
                reason="Begin with due retrieval before new teaching.",
                target_ids=context.due_retrieval_concept_ids,
                return_to_source_spine=context.source_spine,
            )

        if context.source_gap or not context.source_anchor_available:
            return RoutingDecision(
                action=AdaptiveAction.SOURCE_RECOVERY,
                quality_mode=QualityMode.DEEP,
                reason=(
                    "The source target is missing or unresolved; recover the "
                    "original source before teaching the claim."
                ),
                return_to_source_spine=context.source_spine,
            )

        if context.freshness_required and not context.freshness_verified:
            return RoutingDecision(
                action=AdaptiveAction.VERIFY_CURRENT_EVIDENCE,
                quality_mode=QualityMode.CRITICAL,
                reason=(
                    "The current source item is time-sensitive and requires "
                    "current-validity verification before being taught as standard."
                ),
                return_to_source_spine=context.source_spine,
            )

        if context.weak_required_prerequisite_ids:
            return RoutingDecision(
                action=AdaptiveAction.PREREQUISITE_REPAIR,
                quality_mode=quality,
                reason="A required prerequisite is too weak for the current mechanism.",
                target_ids=context.weak_required_prerequisite_ids,
                return_to_source_spine=context.source_spine,
            )

        if context.open_error_ids:
            return RoutingDecision(
                action=AdaptiveAction.ERROR_REMEDIATION,
                quality_mode=quality,
                reason="An observed learner error remains open and should be retested.",
                target_ids=context.open_error_ids,
                return_to_source_spine=context.source_spine,
            )

        if (
            context.current_learning_value == LearningValue.REFERENCE_ONLY
            and not context.learner_requested_reference_detail
        ):
            return RoutingDecision(
                action=AdaptiveAction.REFERENCE_COVERAGE,
                quality_mode=QualityMode.FAST,
                reason=(
                    "Map and briefly cover the reference-only source item without "
                    "turning it into an active mastery target."
                ),
                return_to_source_spine=context.source_spine,
            )

        if context.source_is_insufficient_for_explanation:
            return RoutingDecision(
                action=AdaptiveAction.CROSS_BOOK_EXPANSION,
                quality_mode=quality,
                reason="The source spine needs a bounded supporting-source expansion.",
                return_to_source_spine=context.source_spine,
            )

        if context.ready_for_transfer:
            return RoutingDecision(
                action=AdaptiveAction.TRANSFER,
                quality_mode=quality,
                reason="Mechanistic understanding is sufficient for transfer testing.",
                return_to_source_spine=context.source_spine,
            )

        return RoutingDecision(
            action=AdaptiveAction.CONTINUE_SOURCE_SPINE,
            quality_mode=quality,
            reason="Continue the approved logical-book Source Map position.",
            return_to_source_spine=context.source_spine,
        )

    @staticmethod
    def _quality_mode(context: RoutingContext) -> QualityMode:
        if context.freshness_required:
            return QualityMode.CRITICAL
        if context.concept_is_complex:
            return QualityMode.DEEP
        return QualityMode.FAST
