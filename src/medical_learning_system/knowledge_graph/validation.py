from dataclasses import dataclass

from .schemas import GraphEdge, GraphNode, ValidationStatus


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    reasons: tuple[str, ...]


def validate_for_promotion(item: GraphNode | GraphEdge) -> PromotionDecision:
    """Structural gate before an extracted node/edge may enter the canonical KG."""
    reasons: list[str] = []

    if not item.evidence:
        reasons.append("missing_evidence")

    for evidence in item.evidence:
        locator = evidence.locator
        if locator.page is None and not locator.chapter and not locator.section:
            reasons.append("missing_source_locator")

    if item.validation_status == ValidationStatus.REJECTED:
        reasons.append("already_rejected")

    return PromotionDecision(
        allowed=not reasons,
        reasons=tuple(sorted(set(reasons))),
    )
