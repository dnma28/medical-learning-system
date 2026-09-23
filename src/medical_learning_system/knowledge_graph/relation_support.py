from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field

from .claim_review import ClaimReviewRecord, promotion_blockers
from .v5_migration import RelationKind, V5RelationCandidate


class RelationClaimMappingState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class RelationClaimLink(BaseModel):
    mapping_id: str = Field(min_length=1)
    relation_candidate_id: str = Field(min_length=1)
    claim_review_id: str = Field(min_length=1)
    state: RelationClaimMappingState = RelationClaimMappingState.UNREVIEWED
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    note: str | None = None


class RelationSupportReport(BaseModel):
    relation_candidate_id: str
    relation_kind: RelationKind
    provenance: str | None = None
    confirmed_claim_review_ids: list[str] = Field(default_factory=list)
    rejected_claim_review_ids: list[str] = Field(default_factory=list)
    unreviewed_claim_review_ids: list[str] = Field(default_factory=list)
    support_ready: bool
    source_derived_ready: bool
    support_blockers: list[str] = Field(default_factory=list)
    source_derived_blockers: list[str] = Field(default_factory=list)


def make_relation_claim_link(
    relation_candidate_id: str,
    claim_review_id: str,
) -> RelationClaimLink:
    relation_candidate_id = relation_candidate_id.strip()
    claim_review_id = claim_review_id.strip()
    if not relation_candidate_id or not claim_review_id:
        raise ValueError("relation_candidate_id and claim_review_id are required")

    payload = f"{relation_candidate_id}|{claim_review_id}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return RelationClaimLink(
        mapping_id=f"rel-claim-{digest}",
        relation_candidate_id=relation_candidate_id,
        claim_review_id=claim_review_id,
    )


def review_relation_claim_link(
    link: RelationClaimLink,
    *,
    state: RelationClaimMappingState,
    reviewer: str,
    reviewed_at: datetime,
    note: str | None = None,
) -> RelationClaimLink:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer cannot be empty")
    if state == RelationClaimMappingState.UNREVIEWED:
        raise ValueError("review action must be CONFIRMED or REJECTED")

    return link.model_copy(
        update={
            "state": state,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "note": note,
        }
    )


def relation_support_report(
    relation: V5RelationCandidate,
    *,
    links: Iterable[RelationClaimLink],
    claim_reviews: Iterable[ClaimReviewRecord],
) -> RelationSupportReport:
    review_by_id = {item.review_id: item for item in claim_reviews}
    relation_links = [
        link
        for link in links
        if link.relation_candidate_id == relation.candidate_id
    ]
    _validate_unique_pairs(relation_links)

    confirmed: list[str] = []
    rejected: list[str] = []
    unreviewed: list[str] = []
    support_blockers: list[str] = []
    usable_confirmed = 0

    if not relation_links:
        support_blockers.append("no_explicit_claim_mapping")

    for link in relation_links:
        review = review_by_id.get(link.claim_review_id)
        if review is None:
            support_blockers.append(
                f"unknown_claim_review:{link.claim_review_id}"
            )
            continue

        if link.state == RelationClaimMappingState.REJECTED:
            rejected.append(link.claim_review_id)
            continue
        if link.state == RelationClaimMappingState.UNREVIEWED:
            unreviewed.append(link.claim_review_id)
            continue

        confirmed.append(link.claim_review_id)
        blockers = promotion_blockers(review)
        if blockers.blocked:
            support_blockers.extend(
                f"claim:{review.review_id}:{blocker}"
                for blocker in blockers.blockers
            )
        else:
            usable_confirmed += 1

    if relation_links and not confirmed:
        support_blockers.append("no_confirmed_claim_mapping")
    elif confirmed and usable_confirmed == 0:
        support_blockers.append("no_confirmed_claim_clears_review_gates")

    support_ready = usable_confirmed > 0
    source_derived_blockers = list(dict.fromkeys(support_blockers))

    if (
        relation.kind == RelationKind.BRIDGE
        and (relation.provenance or "").upper() == "INFERRED"
    ):
        source_derived_blockers.append(
            "inferred_bridge_not_source_derived"
        )

    source_derived_ready = (
        support_ready
        and not source_derived_blockers
    )

    return RelationSupportReport(
        relation_candidate_id=relation.candidate_id,
        relation_kind=relation.kind,
        provenance=relation.provenance,
        confirmed_claim_review_ids=sorted(set(confirmed)),
        rejected_claim_review_ids=sorted(set(rejected)),
        unreviewed_claim_review_ids=sorted(set(unreviewed)),
        support_ready=support_ready,
        source_derived_ready=source_derived_ready,
        support_blockers=list(dict.fromkeys(support_blockers)),
        source_derived_blockers=list(
            dict.fromkeys(source_derived_blockers)
        ),
    )


def validate_relation_claim_links(
    *,
    relations: Iterable[V5RelationCandidate],
    claim_reviews: Iterable[ClaimReviewRecord],
    links: Iterable[RelationClaimLink],
) -> None:
    relation_ids = {item.candidate_id for item in relations}
    review_ids = {item.review_id for item in claim_reviews}
    link_list = list(links)
    _validate_unique_pairs(link_list)

    for link in link_list:
        if link.relation_candidate_id not in relation_ids:
            raise ValueError(
                f"unknown relation_candidate_id: {link.relation_candidate_id}"
            )
        if link.claim_review_id not in review_ids:
            raise ValueError(
                f"unknown claim_review_id: {link.claim_review_id}"
            )


def _validate_unique_pairs(links: list[RelationClaimLink]) -> None:
    seen: set[tuple[str, str]] = set()
    for link in links:
        pair = (link.relation_candidate_id, link.claim_review_id)
        if pair in seen:
            raise ValueError(
                "duplicate relation/claim mapping pair: "
                f"{link.relation_candidate_id} -> {link.claim_review_id}"
            )
        seen.add(pair)
