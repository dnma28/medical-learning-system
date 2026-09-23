from datetime import datetime, timezone

import pytest

from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.knowledge_graph.candidate_materialization import (
    CandidateMaterializationError,
    ExplicitRelationAuditBinding,
    assess_candidate_for_canonical_review,
    bind_audit_to_candidate_edge,
    materialize_v5_node,
    materialize_v5_relation,
)
from medical_learning_system.knowledge_graph.claim_audit import (
    ContentFidelityState,
    CurrentValidityState,
    SourceAnchorState,
    make_claim_audit,
)
from medical_learning_system.knowledge_graph.schemas import ValidationStatus
from medical_learning_system.knowledge_graph.v5_migration import (
    RelationKind,
    V5NodeCandidate,
    V5RelationCandidate,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def block():
    return make_evidence_block(
        source_id="costanzo-physical",
        block_index=0,
        page_index=14,
        content_type=EvidenceContentType.TEXT,
        parser="native",
        text="synthetic evidence",
    )


def audit(evidence_id, **updates):
    values = dict(
        patch_id="foundation.electrochemical_membrane.v1",
        claim_text="Na/K ATPase maintains ion gradients",
        source_anchor_id="sa-b08-ch1",
        source_anchor_state=SourceAnchorState.PASS,
        evidence_candidate_ids={evidence_id},
        selected_evidence_ids={evidence_id},
        content_fidelity_state=ContentFidelityState.VERIFIED,
        current_validity_state=CurrentValidityState.NOT_APPLICABLE,
        requires_current_check=False,
        reviewer="reviewer",
        review_method="passage-level-manual",
        reviewed_at=NOW,
    )
    values.update(updates)
    return make_claim_audit(**values)


def relation(kind=RelationKind.ASSERTED, provenance=None):
    return V5RelationCandidate(
        candidate_id="v5rel-1",
        source="na-k-atpase",
        relation="maintains",
        target="Na_gradient",
        kind=kind,
        provenance=provenance,
        raw=["na-k-atpase", "maintains", "Na_gradient"],
        object_index=0,
    )


def test_v5_node_becomes_candidate_without_invented_evidence():
    node = V5NodeCandidate(
        node_id="na-k-atpase",
        labels={"vi": "bơm Na+/K+-ATPase", "en": "Na+/K+-ATPase"},
        raw={"id": "na-k-atpase"},
    )

    result = materialize_v5_node(node, patch_id="patch.v1")

    assert result.label == "bơm Na+/K+-ATPase"
    assert result.node_type == "legacy_v5_candidate"
    assert result.validation_status == ValidationStatus.CANDIDATE
    assert result.evidence == []


def test_plain_relation_is_candidate_without_claim_evidence():
    candidate = relation()
    edge = materialize_v5_relation(candidate, patch_id="patch.v1")

    assert edge.id == candidate.candidate_id
    assert edge.validation_status == ValidationStatus.CANDIDATE
    assert edge.evidence == []
    assert edge.metadata["relation_kind"] == "asserted"


def test_explicit_verified_binding_attaches_only_selected_evidence():
    source_block = block()
    claim_audit = audit(source_block.evidence_id)
    candidate = relation()
    edge = materialize_v5_relation(candidate, patch_id=claim_audit.patch_id)

    bound = bind_audit_to_candidate_edge(
        edge,
        relation=candidate,
        audit=claim_audit,
        binding=ExplicitRelationAuditBinding(
            relation_candidate_id=candidate.candidate_id,
            audit_id=claim_audit.audit_id,
        ),
        evidence_by_id={source_block.evidence_id: source_block},
    )

    assert len(bound.evidence) == 1
    assert bound.evidence[0].locator.source_id == source_block.source_id
    assert bound.evidence[0].locator.page == 15
    assert bound.evidence[0].locator.quote_hash == source_block.content_sha256
    assert bound.metadata["claim_audit_id"] == claim_audit.audit_id


def test_binding_identity_mismatch_fails():
    source_block = block()
    claim_audit = audit(source_block.evidence_id)
    candidate = relation()
    edge = materialize_v5_relation(candidate, patch_id=claim_audit.patch_id)

    with pytest.raises(CandidateMaterializationError, match="binding"):
        bind_audit_to_candidate_edge(
            edge,
            relation=candidate,
            audit=claim_audit,
            binding=ExplicitRelationAuditBinding(
                relation_candidate_id="different",
                audit_id=claim_audit.audit_id,
            ),
            evidence_by_id={source_block.evidence_id: source_block},
        )


def test_missing_selected_evidence_fails():
    source_block = block()
    claim_audit = audit(source_block.evidence_id)
    candidate = relation()
    edge = materialize_v5_relation(candidate, patch_id=claim_audit.patch_id)

    with pytest.raises(CandidateMaterializationError, match="unavailable"):
        bind_audit_to_candidate_edge(
            edge,
            relation=candidate,
            audit=claim_audit,
            binding=ExplicitRelationAuditBinding(
                relation_candidate_id=candidate.candidate_id,
                audit_id=claim_audit.audit_id,
            ),
            evidence_by_id={},
        )


def test_verified_asserted_relation_can_reach_human_review_gate():
    source_block = block()
    claim_audit = audit(source_block.evidence_id)
    candidate = relation()
    edge = bind_audit_to_candidate_edge(
        materialize_v5_relation(candidate, patch_id=claim_audit.patch_id),
        relation=candidate,
        audit=claim_audit,
        binding=ExplicitRelationAuditBinding(
            relation_candidate_id=candidate.candidate_id,
            audit_id=claim_audit.audit_id,
        ),
        evidence_by_id={source_block.evidence_id: source_block},
    )

    decision = assess_candidate_for_canonical_review(
        edge,
        relation=candidate,
        audit=claim_audit,
    )

    assert decision.eligible_for_human_review is True
    assert decision.reasons == ()


def test_inferred_bridge_stays_blocked_from_direct_canonical_review():
    source_block = block()
    claim_audit = audit(source_block.evidence_id)
    candidate = relation(
        kind=RelationKind.BRIDGE,
        provenance="INFERRED",
    )
    edge = bind_audit_to_candidate_edge(
        materialize_v5_relation(candidate, patch_id=claim_audit.patch_id),
        relation=candidate,
        audit=claim_audit,
        binding=ExplicitRelationAuditBinding(
            relation_candidate_id=candidate.candidate_id,
            audit_id=claim_audit.audit_id,
        ),
        evidence_by_id={source_block.evidence_id: source_block},
    )

    decision = assess_candidate_for_canonical_review(
        edge,
        relation=candidate,
        audit=claim_audit,
    )

    assert decision.eligible_for_human_review is False
    assert "bridge_requires_separate_inference_review" in decision.reasons
    assert "inferred_relation_not_direct_source_fact" in decision.reasons


def test_time_sensitive_relation_requires_current_verified():
    source_block = block()
    claim_audit = audit(
        source_block.evidence_id,
        requires_current_check=True,
        current_validity_state=CurrentValidityState.REQUIRES_EXTERNAL_CHECK,
    )
    candidate = relation()
    edge = bind_audit_to_candidate_edge(
        materialize_v5_relation(candidate, patch_id=claim_audit.patch_id),
        relation=candidate,
        audit=claim_audit,
        binding=ExplicitRelationAuditBinding(
            relation_candidate_id=candidate.candidate_id,
            audit_id=claim_audit.audit_id,
        ),
        evidence_by_id={source_block.evidence_id: source_block},
    )

    decision = assess_candidate_for_canonical_review(
        edge,
        relation=candidate,
        audit=claim_audit,
    )

    assert decision.eligible_for_human_review is False
    assert "current_validity_not_verified" in decision.reasons
