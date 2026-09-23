from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .claim_migration import (
    ClaimMigrationLedger,
    ClaimMigrationRecord,
    ClaimMigrationState,
)


class ContentFidelityState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    WRONG_SOURCE = "WRONG_SOURCE"
    UNRESOLVED = "UNRESOLVED"


class CurrentValidityState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BOOK_CURRENT_UNCHECKED = "BOOK_CURRENT_UNCHECKED"
    REQUIRES_EXTERNAL_CHECK = "REQUIRES_EXTERNAL_CHECK"
    CURRENT_VERIFIED = "CURRENT_VERIFIED"
    OUTDATED = "OUTDATED"
    CONTESTED = "CONTESTED"


class ClaimReviewRecord(BaseModel):
    review_id: str = Field(min_length=1)
    patch_ids: list[str]
    claim: str = Field(min_length=1)
    source_anchor_id: str | None = None
    source_anchor_state: str | None = None
    migration_state: ClaimMigrationState
    candidate_evidence_ids: list[str] = Field(default_factory=list)

    content_fidelity_state: ContentFidelityState = (
        ContentFidelityState.UNREVIEWED
    )
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    content_reviewer: str | None = None
    content_reviewed_at: datetime | None = None
    content_review_note: str | None = None

    current_verification_required: bool = False
    current_validity_state: CurrentValidityState | None = None
    current_validity_evidence_refs: list[str] = Field(default_factory=list)
    validity_reviewer: str | None = None
    validity_reviewed_at: datetime | None = None
    validity_review_note: str | None = None


class PromotionBlockerReport(BaseModel):
    review_id: str
    blocked: bool
    blockers: list[str]


def build_claim_review_records(
    ledger: ClaimMigrationLedger,
) -> list[ClaimReviewRecord]:
    records: list[ClaimReviewRecord] = []
    for position, migrated in enumerate(ledger.records):
        if not migrated.claim:
            continue
        records.append(
            ClaimReviewRecord(
                review_id=_review_id(
                    ledger.patch_ids,
                    position,
                    migrated,
                ),
                patch_ids=ledger.patch_ids,
                claim=migrated.claim,
                source_anchor_id=migrated.source_anchor_id,
                source_anchor_state=_source_anchor_state(migrated),
                migration_state=migrated.state,
                candidate_evidence_ids=sorted(set(migrated.evidence_ids)),
            )
        )
    return records


def review_content_fidelity(
    record: ClaimReviewRecord,
    *,
    state: ContentFidelityState,
    supporting_evidence_ids: list[str] = (),
    reviewer: str,
    reviewed_at: datetime,
    note: str | None = None,
) -> ClaimReviewRecord:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer cannot be empty")

    supporting = sorted(set(supporting_evidence_ids))
    unknown = set(supporting) - set(record.candidate_evidence_ids)
    if unknown:
        raise ValueError(
            "supporting evidence must be selected from candidate evidence IDs"
        )

    if state == ContentFidelityState.VERIFIED:
        if record.migration_state != ClaimMigrationState.PASS_CANDIDATE_EVIDENCE:
            raise ValueError(
                "VERIFIED requires a PASS claim with candidate evidence"
            )
        if (record.source_anchor_state or "").upper() != "PASS":
            raise ValueError("VERIFIED requires source_anchor_state PASS")
        if not supporting:
            raise ValueError(
                "VERIFIED requires explicit supporting evidence IDs"
            )

    if state == ContentFidelityState.PARTIAL and not supporting:
        raise ValueError(
            "PARTIAL requires at least one explicit supporting evidence ID"
        )

    if state in {
        ContentFidelityState.UNSUPPORTED,
        ContentFidelityState.WRONG_SOURCE,
        ContentFidelityState.UNRESOLVED,
    } and supporting:
        raise ValueError(
            f"{state.value} cannot declare supporting evidence IDs"
        )

    return record.model_copy(
        update={
            "content_fidelity_state": state,
            "supporting_evidence_ids": supporting,
            "content_reviewer": reviewer,
            "content_reviewed_at": reviewed_at,
            "content_review_note": note,
        }
    )


def set_current_verification_requirement(
    record: ClaimReviewRecord,
    *,
    required: bool,
) -> ClaimReviewRecord:
    return record.model_copy(
        update={"current_verification_required": required}
    )


def review_current_validity(
    record: ClaimReviewRecord,
    *,
    state: CurrentValidityState,
    reviewer: str,
    reviewed_at: datetime,
    evidence_refs: list[str] = (),
    note: str | None = None,
) -> ClaimReviewRecord:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer cannot be empty")

    refs = sorted({ref.strip() for ref in evidence_refs if ref.strip()})
    evidence_required = {
        CurrentValidityState.CURRENT_VERIFIED,
        CurrentValidityState.OUTDATED,
        CurrentValidityState.CONTESTED,
    }
    if state in evidence_required and not refs:
        raise ValueError(
            f"{state.value} requires current-validity evidence references"
        )

    return record.model_copy(
        update={
            "current_validity_state": state,
            "current_validity_evidence_refs": refs,
            "validity_reviewer": reviewer,
            "validity_reviewed_at": reviewed_at,
            "validity_review_note": note,
        }
    )


def promotion_blockers(record: ClaimReviewRecord) -> PromotionBlockerReport:
    blockers: list[str] = []

    if record.migration_state != ClaimMigrationState.PASS_CANDIDATE_EVIDENCE:
        blockers.append("migration_not_pass_candidate_evidence")

    if (record.source_anchor_state or "").upper() != "PASS":
        blockers.append("source_anchor_not_pass")

    if not record.candidate_evidence_ids:
        blockers.append("missing_candidate_evidence")

    if record.content_fidelity_state != ContentFidelityState.VERIFIED:
        blockers.append("content_fidelity_not_verified")

    if not record.supporting_evidence_ids:
        blockers.append("missing_claim_supporting_evidence")

    state = record.current_validity_state
    if state is None:
        blockers.append("current_validity_unreviewed")
    elif record.current_verification_required:
        if state != CurrentValidityState.CURRENT_VERIFIED:
            blockers.append("current_verification_required")
    elif state not in {
        CurrentValidityState.NOT_APPLICABLE,
        CurrentValidityState.CURRENT_VERIFIED,
    }:
        blockers.append(
            f"current_validity_{state.value.lower()}"
        )

    if (
        state == CurrentValidityState.CURRENT_VERIFIED
        and not record.current_validity_evidence_refs
    ):
        blockers.append("missing_current_validity_evidence")

    return PromotionBlockerReport(
        review_id=record.review_id,
        blocked=bool(blockers),
        blockers=blockers,
    )


def _source_anchor_state(record: ClaimMigrationRecord) -> str | None:
    if record.anchor_resolution is None:
        return None
    return record.anchor_resolution.anchor_verification_state


def _review_id(
    patch_ids: list[str],
    position: int,
    record: ClaimMigrationRecord,
) -> str:
    payload = "|".join(
        [
            ",".join(sorted(patch_ids)),
            str(position),
            record.source_anchor_id or "",
            record.claim or "",
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"claim-review-{digest}"
