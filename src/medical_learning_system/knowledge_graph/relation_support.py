from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field

from .claim_audit import ClaimAuditRecord, assess_claim_audit
from .v5_migration import RelationKind, V5RelationCandidate


class RelationAuditMappingState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class RelationAuditLink(BaseModel):
    mapping_id: str = Field(min_length=1)
    relation_candidate_id: str = Field(min_length=1)
    audit_id: str = Field(min_length=1)
    state: RelationAuditMappingState = RelationAuditMappingState.UNREVIEWED
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    note: str | None = None


class RelationSupportReport(BaseModel):
    relation_candidate_id: str
    relation_kind: RelationKind
    provenance: str | None = None

    confirmed_audit_ids: list[str] = Field(default_factory=list)
    rejected_audit_ids: list[str] = Field(default_factory=list)
    unreviewed_audit_ids: list[str] = Field(default_factory=list)

    source_grounded_ready: bool
    current_standard_ready: bool
    source_derived_ready: bool
    current_standard_source_derived_ready: bool

    source_grounded_blockers: list[str] = Field(default_factory=list)
    current_standard_blockers: list[str] = Field(default_factory=list)
    source_derived_blockers: list[str] = Field(default_factory=list)


def make_relation_audit_link(
    relation_candidate_id: str,
    audit_id: str,
) -> RelationAuditLink:
    relation_candidate_id = relation_candidate_id.strip()
    audit_id = audit_id.strip()
    if not relation_candidate_id or not audit_id:
        raise ValueError("relation_candidate_id and audit_id are required")

    identity = f"{relation_candidate_id}|{audit_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return RelationAuditLink(
        mapping_id=f"rel-audit-{digest}",
        relation_candidate_id=relation_candidate_id,
        audit_id=audit_id,
    )


def review_relation_audit_link(
    link: RelationAuditLink,
    *,
    state: RelationAuditMappingState,
    reviewer: str,
    reviewed_at: datetime,
    note: str | None = None,
) -> RelationAuditLink:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer cannot be empty")
    if state == RelationAuditMappingState.UNREVIEWED:
        raise ValueError("review action must be CONFIRMED or REJECTED")

    return link.model_copy(
        update={
            "state": state,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "note": note,
        }
    )


def validate_relation_audit_links(
    *,
    relations: Iterable[V5RelationCandidate],
    audits: Iterable[ClaimAuditRecord],
    links: Iterable[RelationAuditLink],
) -> None:
    relation_ids = {item.candidate_id for item in relations}
    audit_ids = {item.audit_id for item in audits}
    link_list = list(links)
    _validate_unique_pairs(link_list)

    for link in link_list:
        if link.relation_candidate_id not in relation_ids:
            raise ValueError(
                f"unknown relation_candidate_id: {link.relation_candidate_id}"
            )
        if link.audit_id not in audit_ids:
            raise ValueError(f"unknown audit_id: {link.audit_id}")


def relation_support_report(
    relation: V5RelationCandidate,
    *,
    links: Iterable[RelationAuditLink],
    audits: Iterable[ClaimAuditRecord],
) -> RelationSupportReport:
    audit_by_id = {item.audit_id: item for item in audits}
    relation_links = [
        link
        for link in links
        if link.relation_candidate_id == relation.candidate_id
    ]
    _validate_unique_pairs(relation_links)

    confirmed: list[str] = []
    rejected: list[str] = []
    unreviewed: list[str] = []

    grounded_blockers: list[str] = []
    current_blockers: list[str] = []
    grounded_count = 0
    current_count = 0

    if not relation_links:
        grounded_blockers.append("no_explicit_claim_audit_mapping")
        current_blockers.append("no_explicit_claim_audit_mapping")

    for link in relation_links:
        audit = audit_by_id.get(link.audit_id)
        if audit is None:
            blocker = f"unknown_audit:{link.audit_id}"
            grounded_blockers.append(blocker)
            current_blockers.append(blocker)
            continue

        if link.state == RelationAuditMappingState.REJECTED:
            rejected.append(link.audit_id)
            continue

        if link.state == RelationAuditMappingState.UNREVIEWED:
            unreviewed.append(link.audit_id)
            continue

        confirmed.append(link.audit_id)
        decision = assess_claim_audit(audit)

        if decision.source_grounded_ready:
            grounded_count += 1
        else:
            grounded_blockers.extend(
                f"audit:{audit.audit_id}:{reason}"
                for reason in decision.reasons
                if reason
                in {
                    "source_anchor_not_pass",
                    "content_fidelity_not_verified",
                    "missing_selected_evidence",
                }
            )

        if decision.current_standard_ready:
            current_count += 1
        else:
            current_blockers.extend(
                f"audit:{audit.audit_id}:{reason}"
                for reason in decision.reasons
            )

    if relation_links and not confirmed:
        grounded_blockers.append("no_confirmed_claim_audit_mapping")
        current_blockers.append("no_confirmed_claim_audit_mapping")
    elif confirmed and grounded_count == 0:
        grounded_blockers.append("no_confirmed_audit_is_source_grounded")
    elif confirmed and current_count == 0:
        current_blockers.append("no_confirmed_audit_is_current_standard")

    source_grounded_ready = grounded_count > 0
    current_standard_ready = current_count > 0

    source_derived_blockers = list(dict.fromkeys(grounded_blockers))
    inferred_bridge = (
        relation.kind == RelationKind.BRIDGE
        and (relation.provenance or "").upper() == "INFERRED"
    )
    if inferred_bridge:
        source_derived_blockers.append("inferred_bridge_not_source_derived")

    source_derived_ready = (
        source_grounded_ready
        and not source_derived_blockers
    )
    current_standard_source_derived_ready = (
        current_standard_ready
        and source_derived_ready
    )

    return RelationSupportReport(
        relation_candidate_id=relation.candidate_id,
        relation_kind=relation.kind,
        provenance=relation.provenance,
        confirmed_audit_ids=sorted(set(confirmed)),
        rejected_audit_ids=sorted(set(rejected)),
        unreviewed_audit_ids=sorted(set(unreviewed)),
        source_grounded_ready=source_grounded_ready,
        current_standard_ready=current_standard_ready,
        source_derived_ready=source_derived_ready,
        current_standard_source_derived_ready=(
            current_standard_source_derived_ready
        ),
        source_grounded_blockers=list(dict.fromkeys(grounded_blockers)),
        current_standard_blockers=list(dict.fromkeys(current_blockers)),
        source_derived_blockers=list(
            dict.fromkeys(source_derived_blockers)
        ),
    )


def _validate_unique_pairs(links: list[RelationAuditLink]) -> None:
    seen: set[tuple[str, str]] = set()
    for link in links:
        pair = (link.relation_candidate_id, link.audit_id)
        if pair in seen:
            raise ValueError(
                "duplicate relation/audit mapping pair: "
                f"{link.relation_candidate_id} -> {link.audit_id}"
            )
        seen.add(pair)
