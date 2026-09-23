from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, Field

from ..evidence_store import SourceEvidenceBlock
from ..source_registry import SourceRecord
from .source_anchor_resolution import (
    AnchorIdentityState,
    LegacySourceMap,
    SourceAnchorResolution,
    resolve_source_anchor,
)
from .v5_migration import V5PatchMigration


class ClaimMigrationState(str, Enum):
    PASS_CANDIDATE_EVIDENCE = "pass_candidate_evidence"
    PASS_NO_EVIDENCE_CANDIDATES = "pass_no_evidence_candidates"
    PASS_SOURCE_UNRESOLVED = "pass_source_unresolved"
    GAP = "gap"
    MISMATCH = "mismatch"
    VERIFICATION_CONFLICT = "verification_conflict"
    MISSING_ANCHOR_REFERENCE = "missing_anchor_reference"
    UNKNOWN_ANCHOR_REFERENCE = "unknown_anchor_reference"
    AMBIGUOUS_ANCHOR_REFERENCE = "ambiguous_anchor_reference"
    UNREVIEWED = "unreviewed"
    INVALID_CLAIM = "invalid_claim"


class ClaimMigrationRecord(BaseModel):
    claim: str | None = None
    verification_state: str | None = None
    source_anchor_id: str | None = None
    state: ClaimMigrationState
    anchor_resolution: SourceAnchorResolution | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    passage_review_required: bool = True
    notes: list[str] = Field(default_factory=list)
    raw: dict[str, Any]


class ClaimMigrationLedger(BaseModel):
    patch_ids: list[str]
    total_claims: int
    states: dict[str, int]
    records: list[ClaimMigrationRecord]


def build_claim_migration_ledger(
    migration: V5PatchMigration,
    *,
    source_map: LegacySourceMap,
    sources: Iterable[SourceRecord],
    evidence: Iterable[SourceEvidenceBlock] = (),
) -> ClaimMigrationLedger:
    source_list = list(sources)
    evidence_list = list(evidence)

    anchors_by_id: dict[str, list[dict[str, Any]]] = {}
    for anchor in migration.source_anchors:
        anchor_id = _string(anchor.get("id"))
        if anchor_id is not None:
            anchors_by_id.setdefault(anchor_id, []).append(anchor)

    records = [
        _resolve_claim(
            raw,
            anchors_by_id=anchors_by_id,
            source_map=source_map,
            sources=source_list,
            evidence=evidence_list,
        )
        for raw in migration.claim_verification
    ]
    counts = Counter(record.state.value for record in records)

    return ClaimMigrationLedger(
        patch_ids=migration.patch_ids,
        total_claims=len(records),
        states=dict(sorted(counts.items())),
        records=records,
    )


def _resolve_claim(
    raw: dict[str, Any],
    *,
    anchors_by_id: dict[str, list[dict[str, Any]]],
    source_map: LegacySourceMap,
    sources: list[SourceRecord],
    evidence: list[SourceEvidenceBlock],
) -> ClaimMigrationRecord:
    claim = _string(raw.get("claim"))
    verification = _string(raw.get("verification_state"))
    anchor_id = _string(raw.get("source_anchor_id"))

    if claim is None:
        return ClaimMigrationRecord(
            verification_state=verification,
            source_anchor_id=anchor_id,
            state=ClaimMigrationState.INVALID_CLAIM,
            notes=["claim_verification entry has no usable claim text"],
            raw=raw,
        )

    normalized_state = (verification or "").upper()

    if anchor_id is None:
        if normalized_state == "GAP":
            return ClaimMigrationRecord(
                claim=claim,
                verification_state=verification,
                state=ClaimMigrationState.GAP,
                notes=[
                    "claim is explicitly GAP and has no source_anchor_id"
                ],
                raw=raw,
            )
        if normalized_state == "MISMATCH":
            return ClaimMigrationRecord(
                claim=claim,
                verification_state=verification,
                state=ClaimMigrationState.MISMATCH,
                notes=[
                    "claim is explicitly MISMATCH and has no source_anchor_id"
                ],
                raw=raw,
            )
        return ClaimMigrationRecord(
            claim=claim,
            verification_state=verification,
            state=ClaimMigrationState.MISSING_ANCHOR_REFERENCE,
            notes=["claim has no explicit source_anchor_id"],
            raw=raw,
        )

    matches = anchors_by_id.get(anchor_id, [])
    if not matches:
        return ClaimMigrationRecord(
            claim=claim,
            verification_state=verification,
            source_anchor_id=anchor_id,
            state=ClaimMigrationState.UNKNOWN_ANCHOR_REFERENCE,
            notes=[f"source_anchor_id {anchor_id!r} was not found in patch"],
            raw=raw,
        )
    if len(matches) > 1:
        return ClaimMigrationRecord(
            claim=claim,
            verification_state=verification,
            source_anchor_id=anchor_id,
            state=ClaimMigrationState.AMBIGUOUS_ANCHOR_REFERENCE,
            notes=[f"source_anchor_id {anchor_id!r} is duplicated in patch"],
            raw=raw,
        )

    resolution = resolve_source_anchor(
        matches[0],
        source_map=source_map,
        sources=sources,
        evidence=evidence,
    )
    anchor_state = (resolution.anchor_verification_state or "").upper()

    if normalized_state == "GAP":
        return _record(
            claim, verification, anchor_id, ClaimMigrationState.GAP,
            resolution, raw,
            "claim verification is GAP; resolver cannot upgrade it",
        )
    if normalized_state == "MISMATCH":
        return _record(
            claim, verification, anchor_id, ClaimMigrationState.MISMATCH,
            resolution, raw,
            "claim verification is MISMATCH; resolver cannot upgrade it",
        )

    if normalized_state == "PASS":
        if anchor_state != "PASS":
            return _record(
                claim, verification, anchor_id,
                ClaimMigrationState.VERIFICATION_CONFLICT,
                resolution, raw,
                (
                    f"claim is PASS but source anchor is "
                    f"{anchor_state or 'UNSPECIFIED'}"
                ),
            )
        if resolution.identity_state != AnchorIdentityState.RESOLVED:
            return _record(
                claim, verification, anchor_id,
                ClaimMigrationState.PASS_SOURCE_UNRESOLVED,
                resolution, raw,
                "claim is PASS but source identity is not resolved",
            )
        if resolution.evidence_candidates_resolved:
            return ClaimMigrationRecord(
                claim=claim,
                verification_state=verification,
                source_anchor_id=anchor_id,
                state=ClaimMigrationState.PASS_CANDIDATE_EVIDENCE,
                anchor_resolution=resolution,
                evidence_ids=resolution.evidence_ids,
                passage_review_required=True,
                notes=[
                    "page-level evidence candidates found; exact claim-support "
                    "passage review is still required before KG promotion"
                ],
                raw=raw,
            )
        return _record(
            claim, verification, anchor_id,
            ClaimMigrationState.PASS_NO_EVIDENCE_CANDIDATES,
            resolution, raw,
            "claim is PASS but no stored page-level evidence candidate resolved",
        )

    return _record(
        claim, verification, anchor_id,
        ClaimMigrationState.UNREVIEWED,
        resolution, raw,
        "claim verification state is neither PASS, GAP nor MISMATCH",
    )


def _record(
    claim: str,
    verification: str | None,
    anchor_id: str,
    state: ClaimMigrationState,
    resolution: SourceAnchorResolution,
    raw: dict[str, Any],
    note: str,
) -> ClaimMigrationRecord:
    return ClaimMigrationRecord(
        claim=claim,
        verification_state=verification,
        source_anchor_id=anchor_id,
        state=state,
        anchor_resolution=resolution,
        evidence_ids=resolution.evidence_ids,
        passage_review_required=True,
        notes=[note],
        raw=raw,
    )


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
