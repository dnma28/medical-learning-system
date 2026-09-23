from datetime import datetime, timezone

import pytest

from medical_learning_system.knowledge_graph.claim_migration import (
    ClaimMigrationState,
)
from medical_learning_system.knowledge_graph.claim_review import (
    ClaimReviewRecord,
    ContentFidelityState,
    CurrentValidityState,
)
from medical_learning_system.knowledge_graph.relation_support import (
    RelationClaimMappingState,
    make_relation_claim_link,
    relation_support_report,
    review_relation_claim_link,
    validate_relation_claim_links,
)
from medical_learning_system.knowledge_graph.v5_migration import (
    RelationKind,
    V5RelationCandidate,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def relation(
    *,
    relation_id="v5rel-edge",
    kind=RelationKind.ASSERTED,
    provenance=None,
):
    return V5RelationCandidate(
        candidate_id=relation_id,
        source="na-k-atpase",
        relation="maintains",
        target="Na_gradient",
        kind=kind,
        provenance=provenance,
        raw=["na-k-atpase", "maintains", "Na_gradient"],
        object_index=0,
    )


def reviewed_claim(
    *,
    review_id="claim-review-1",
    validity=CurrentValidityState.NOT_APPLICABLE,
):
    refs = (
        ["guideline:2026:abc"]
        if validity == CurrentValidityState.CURRENT_VERIFIED
        else []
    )
    return ClaimReviewRecord(
        review_id=review_id,
        patch_ids=["foundation.electrochemical_membrane.v1"],
        claim="Na/K ATPase maintains sodium and potassium gradients",
        source_anchor_id="sa-b08-ch1",
        source_anchor_state="PASS",
        migration_state=ClaimMigrationState.PASS_CANDIDATE_EVIDENCE,
        candidate_evidence_ids=["ev-1", "ev-2"],
        content_fidelity_state=ContentFidelityState.VERIFIED,
        supporting_evidence_ids=["ev-1"],
        content_reviewer="reviewer",
        content_reviewed_at=NOW,
        current_validity_state=validity,
        current_validity_evidence_refs=refs,
        validity_reviewer="reviewer",
        validity_reviewed_at=NOW,
    )


def confirmed_link(rel_id="v5rel-edge", review_id="claim-review-1"):
    return review_relation_claim_link(
        make_relation_claim_link(rel_id, review_id),
        state=RelationClaimMappingState.CONFIRMED,
        reviewer="reviewer",
        reviewed_at=NOW,
    )


def test_unreviewed_mapping_does_not_support_relation():
    rel = relation()
    link = make_relation_claim_link(rel.candidate_id, "claim-review-1")

    report = relation_support_report(
        rel,
        links=[link],
        claim_reviews=[reviewed_claim()],
    )

    assert report.support_ready is False
    assert report.unreviewed_claim_review_ids == ["claim-review-1"]
    assert "no_confirmed_claim_mapping" in report.support_blockers


def test_confirmed_reviewed_claim_can_support_asserted_relation():
    rel = relation()
    link = confirmed_link()

    report = relation_support_report(
        rel,
        links=[link],
        claim_reviews=[reviewed_claim()],
    )

    assert report.support_ready is True
    assert report.source_derived_ready is True
    assert report.support_blockers == []
    assert report.source_derived_blockers == []


def test_inferred_bridge_never_becomes_source_derived_by_mapping():
    rel = relation(
        relation_id="v5rel-bridge",
        kind=RelationKind.BRIDGE,
        provenance="INFERRED",
    )
    link = confirmed_link("v5rel-bridge")

    report = relation_support_report(
        rel,
        links=[link],
        claim_reviews=[reviewed_claim()],
    )

    assert report.support_ready is True
    assert report.source_derived_ready is False
    assert "inferred_bridge_not_source_derived" in (
        report.source_derived_blockers
    )


def test_rejected_mapping_remains_visible():
    rel = relation()
    link = review_relation_claim_link(
        make_relation_claim_link(rel.candidate_id, "claim-review-1"),
        state=RelationClaimMappingState.REJECTED,
        reviewer="reviewer",
        reviewed_at=NOW,
        note="Claim does not entail this exact edge.",
    )

    report = relation_support_report(
        rel,
        links=[link],
        claim_reviews=[reviewed_claim()],
    )

    assert report.rejected_claim_review_ids == ["claim-review-1"]
    assert report.support_ready is False


def test_confirmed_mapping_cannot_bypass_claim_review_blockers():
    rel = relation()
    blocked = reviewed_claim()
    blocked = blocked.model_copy(
        update={
            "content_fidelity_state": ContentFidelityState.UNREVIEWED,
            "supporting_evidence_ids": [],
        }
    )

    report = relation_support_report(
        rel,
        links=[confirmed_link()],
        claim_reviews=[blocked],
    )

    assert report.support_ready is False
    assert any(
        "content_fidelity_not_verified" in blocker
        for blocker in report.support_blockers
    )


def test_duplicate_relation_claim_pair_is_rejected():
    rel = relation()
    link = make_relation_claim_link(rel.candidate_id, "claim-review-1")

    with pytest.raises(ValueError, match="duplicate"):
        validate_relation_claim_links(
            relations=[rel],
            claim_reviews=[reviewed_claim()],
            links=[link, link.model_copy()],
        )


def test_unknown_relation_or_claim_ids_are_rejected():
    rel = relation()

    with pytest.raises(ValueError, match="unknown relation"):
        validate_relation_claim_links(
            relations=[rel],
            claim_reviews=[reviewed_claim()],
            links=[make_relation_claim_link("missing", "claim-review-1")],
        )

    with pytest.raises(ValueError, match="unknown claim"):
        validate_relation_claim_links(
            relations=[rel],
            claim_reviews=[reviewed_claim()],
            links=[make_relation_claim_link(rel.candidate_id, "missing")],
        )
