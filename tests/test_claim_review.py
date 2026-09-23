from datetime import datetime, timezone

import pytest

from medical_learning_system.knowledge_graph.claim_migration import (
    ClaimMigrationLedger,
    ClaimMigrationRecord,
    ClaimMigrationState,
)
from medical_learning_system.knowledge_graph.claim_review import (
    ContentFidelityState,
    CurrentValidityState,
    build_claim_review_records,
    promotion_blockers,
    review_content_fidelity,
    review_current_validity,
    set_current_verification_requirement,
)
from medical_learning_system.knowledge_graph.source_anchor_resolution import (
    AnchorIdentityState,
    SourceAnchorResolution,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def migrated(
    *,
    state=ClaimMigrationState.PASS_CANDIDATE_EVIDENCE,
    anchor_state="PASS",
    evidence_ids=None,
):
    evidence_ids = evidence_ids or ["ev-1", "ev-2"]
    return ClaimMigrationRecord(
        claim="Na/K ATPase maintains Na and K gradients",
        verification_state="PASS",
        source_anchor_id="sa-b08-ch1",
        state=state,
        anchor_resolution=SourceAnchorResolution(
            anchor_id="sa-b08-ch1",
            legacy_source_book_id="b08",
            logical_source_id="costanzo-physiology",
            source_id="costanzo-physical",
            anchor_verification_state=anchor_state,
            identity_state=AnchorIdentityState.RESOLVED,
            explicit_pdf_pages=[15],
            evidence_ids=evidence_ids,
            evidence_candidates_resolved=bool(evidence_ids),
        ),
        evidence_ids=evidence_ids,
        raw={"claim": "Na/K ATPase maintains Na and K gradients"},
    )


def record():
    ledger = ClaimMigrationLedger(
        patch_ids=["foundation.electrochemical_membrane.v1"],
        total_claims=1,
        states={"pass_candidate_evidence": 1},
        records=[migrated()],
    )
    return build_claim_review_records(ledger)[0]


def test_build_review_record_does_not_auto_verify_claim():
    item = record()

    assert item.content_fidelity_state == ContentFidelityState.UNREVIEWED
    assert item.current_validity_state is None
    assert item.candidate_evidence_ids == ["ev-1", "ev-2"]
    assert promotion_blockers(item).blocked is True


def test_verified_content_requires_explicit_supporting_block_subset():
    item = review_content_fidelity(
        record(),
        state=ContentFidelityState.VERIFIED,
        supporting_evidence_ids=["ev-2"],
        reviewer="reviewer-1",
        reviewed_at=NOW,
        note="Exact supporting passage selected.",
    )

    assert item.supporting_evidence_ids == ["ev-2"]
    assert item.content_reviewer == "reviewer-1"

    with pytest.raises(ValueError, match="candidate evidence"):
        review_content_fidelity(
            record(),
            state=ContentFidelityState.VERIFIED,
            supporting_evidence_ids=["ev-outside"],
            reviewer="reviewer-1",
            reviewed_at=NOW,
        )


def test_verified_content_cannot_upgrade_gap_or_unresolved_migration():
    gap = migrated(
        state=ClaimMigrationState.GAP,
        anchor_state="GAP",
    )
    ledger = ClaimMigrationLedger(
        patch_ids=["p"],
        total_claims=1,
        states={"gap": 1},
        records=[gap],
    )
    item = build_claim_review_records(ledger)[0]

    with pytest.raises(ValueError, match="PASS claim"):
        review_content_fidelity(
            item,
            state=ContentFidelityState.VERIFIED,
            supporting_evidence_ids=["ev-1"],
            reviewer="reviewer",
            reviewed_at=NOW,
        )


def test_partial_review_requires_selected_supporting_evidence():
    with pytest.raises(ValueError, match="PARTIAL"):
        review_content_fidelity(
            record(),
            state=ContentFidelityState.PARTIAL,
            reviewer="reviewer",
            reviewed_at=NOW,
        )


def test_current_verified_requires_external_evidence_reference():
    item = record()

    with pytest.raises(ValueError, match="requires current-validity"):
        review_current_validity(
            item,
            state=CurrentValidityState.CURRENT_VERIFIED,
            reviewer="reviewer",
            reviewed_at=NOW,
        )

    reviewed = review_current_validity(
        item,
        state=CurrentValidityState.CURRENT_VERIFIED,
        reviewer="reviewer",
        reviewed_at=NOW,
        evidence_refs=["guideline:2026:abc"],
    )
    assert reviewed.current_validity_evidence_refs == ["guideline:2026:abc"]


def test_non_time_sensitive_verified_claim_can_clear_blockers_as_not_applicable():
    item = review_content_fidelity(
        record(),
        state=ContentFidelityState.VERIFIED,
        supporting_evidence_ids=["ev-1"],
        reviewer="reviewer",
        reviewed_at=NOW,
    )
    item = review_current_validity(
        item,
        state=CurrentValidityState.NOT_APPLICABLE,
        reviewer="reviewer",
        reviewed_at=NOW,
        note="Stable basic physiology concept.",
    )

    report = promotion_blockers(item)

    assert report.blocked is False
    assert report.blockers == []


def test_time_sensitive_claim_requires_current_verified():
    item = review_content_fidelity(
        record(),
        state=ContentFidelityState.VERIFIED,
        supporting_evidence_ids=["ev-1"],
        reviewer="reviewer",
        reviewed_at=NOW,
    )
    item = set_current_verification_requirement(item, required=True)
    item = review_current_validity(
        item,
        state=CurrentValidityState.NOT_APPLICABLE,
        reviewer="reviewer",
        reviewed_at=NOW,
    )

    report = promotion_blockers(item)

    assert report.blocked is True
    assert "current_verification_required" in report.blockers


def test_book_current_unchecked_remains_blocked():
    item = review_content_fidelity(
        record(),
        state=ContentFidelityState.VERIFIED,
        supporting_evidence_ids=["ev-1"],
        reviewer="reviewer",
        reviewed_at=NOW,
    )
    item = review_current_validity(
        item,
        state=CurrentValidityState.BOOK_CURRENT_UNCHECKED,
        reviewer="reviewer",
        reviewed_at=NOW,
    )

    assert "current_validity_book_current_unchecked" in (
        promotion_blockers(item).blockers
    )
