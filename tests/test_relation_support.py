from datetime import datetime, timezone

import pytest

from medical_learning_system.knowledge_graph.claim_audit import (
    ContentFidelityState,
    CurrentValidityState,
    SourceAnchorState,
    make_claim_audit,
)
from medical_learning_system.knowledge_graph.relation_support import (
    RelationAuditMappingState,
    make_relation_audit_link,
    relation_support_report,
    review_relation_audit_link,
    validate_relation_audit_links,
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


def audit(
    *,
    audit_id=None,
    current=CurrentValidityState.NOT_APPLICABLE,
    requires_current=False,
    fidelity=ContentFidelityState.VERIFIED,
):
    item = make_claim_audit(
        patch_id="foundation.electrochemical_membrane.v1",
        claim_text="Na/K ATPase maintains sodium and potassium gradients",
        source_anchor_id="sa-b08-ch1",
        source_anchor_state=SourceAnchorState.PASS,
        evidence_candidate_ids={"ev-1", "ev-2"},
        selected_evidence_ids={"ev-1"},
        content_fidelity_state=fidelity,
        current_validity_state=current,
        requires_current_check=requires_current,
        reviewer="reviewer",
        review_method="passage-level-manual",
        reviewed_at=NOW,
    )
    return item if audit_id is None else item.model_copy(
        update={"audit_id": audit_id}
    )


def confirmed_link(rel_id="v5rel-edge", audit_id="audit-1"):
    return review_relation_audit_link(
        make_relation_audit_link(rel_id, audit_id),
        state=RelationAuditMappingState.CONFIRMED,
        reviewer="relation-reviewer",
        reviewed_at=NOW,
    )


def test_unreviewed_mapping_does_not_support_relation():
    rel = relation()
    item = audit(audit_id="audit-1")
    link = make_relation_audit_link(rel.candidate_id, item.audit_id)

    report = relation_support_report(
        rel,
        links=[link],
        audits=[item],
    )

    assert report.source_grounded_ready is False
    assert report.unreviewed_audit_ids == ["audit-1"]
    assert "no_confirmed_claim_audit_mapping" in (
        report.source_grounded_blockers
    )


def test_confirmed_source_grounded_audit_supports_asserted_relation():
    rel = relation()
    item = audit(audit_id="audit-1")

    report = relation_support_report(
        rel,
        links=[confirmed_link()],
        audits=[item],
    )

    assert report.source_grounded_ready is True
    assert report.current_standard_ready is True
    assert report.source_derived_ready is True
    assert report.current_standard_source_derived_ready is True
    assert report.source_derived_blockers == []


def test_inferred_bridge_stays_inferred_even_with_grounded_audit():
    rel = relation(
        relation_id="v5rel-bridge",
        kind=RelationKind.BRIDGE,
        provenance="INFERRED",
    )
    item = audit(audit_id="audit-1")

    report = relation_support_report(
        rel,
        links=[confirmed_link("v5rel-bridge")],
        audits=[item],
    )

    assert report.source_grounded_ready is True
    assert report.current_standard_ready is True
    assert report.source_derived_ready is False
    assert report.current_standard_source_derived_ready is False
    assert "inferred_bridge_not_source_derived" in (
        report.source_derived_blockers
    )


def test_rejected_mapping_remains_visible():
    rel = relation()
    item = audit(audit_id="audit-1")
    link = review_relation_audit_link(
        make_relation_audit_link(rel.candidate_id, item.audit_id),
        state=RelationAuditMappingState.REJECTED,
        reviewer="relation-reviewer",
        reviewed_at=NOW,
        note="The claim does not entail this exact edge.",
    )

    report = relation_support_report(
        rel,
        links=[link],
        audits=[item],
    )

    assert report.rejected_audit_ids == ["audit-1"]
    assert report.source_grounded_ready is False


def test_confirmed_mapping_cannot_bypass_claim_audit_gate():
    rel = relation()
    item = audit(
        audit_id="audit-1",
        fidelity=ContentFidelityState.PARTIAL,
    )

    report = relation_support_report(
        rel,
        links=[confirmed_link()],
        audits=[item],
    )

    assert report.source_grounded_ready is False
    assert any(
        "content_fidelity_not_verified" in blocker
        for blocker in report.source_grounded_blockers
    )


def test_current_standard_readiness_is_separate_from_source_grounding():
    rel = relation()
    item = audit(
        audit_id="audit-1",
        current=CurrentValidityState.BOOK_CURRENT_UNCHECKED,
    )

    report = relation_support_report(
        rel,
        links=[confirmed_link()],
        audits=[item],
    )

    assert report.source_grounded_ready is True
    assert report.current_standard_ready is False
    assert report.source_derived_ready is True
    assert report.current_standard_source_derived_ready is False


def test_duplicate_relation_audit_pair_is_rejected():
    rel = relation()
    item = audit(audit_id="audit-1")
    link = make_relation_audit_link(rel.candidate_id, item.audit_id)

    with pytest.raises(ValueError, match="duplicate"):
        validate_relation_audit_links(
            relations=[rel],
            audits=[item],
            links=[link, link.model_copy()],
        )


def test_unknown_relation_or_audit_is_rejected():
    rel = relation()
    item = audit(audit_id="audit-1")

    with pytest.raises(ValueError, match="unknown relation"):
        validate_relation_audit_links(
            relations=[rel],
            audits=[item],
            links=[make_relation_audit_link("missing", item.audit_id)],
        )

    with pytest.raises(ValueError, match="unknown audit"):
        validate_relation_audit_links(
            relations=[rel],
            audits=[item],
            links=[make_relation_audit_link(rel.candidate_id, "missing")],
        )
