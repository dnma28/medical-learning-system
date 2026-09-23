from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from medical_learning_system.knowledge_graph.claim_audit import (
    ClaimAuditStore,
    ContentFidelityState,
    CurrentValidityState,
    SourceAnchorState,
    assess_claim_audit,
    make_claim_audit,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def audit(**updates):
    values = {
        "patch_id": "foundation.homeostasis.v1",
        "claim_text": "homeostasis is dynamic rather than static constancy",
        "source_anchor_id": "sa-b04-ch1-homeostasis",
        "source_anchor_state": SourceAnchorState.PASS,
        "evidence_candidate_ids": {"ev-1", "ev-2"},
        "selected_evidence_ids": {"ev-1"},
        "content_fidelity_state": ContentFidelityState.VERIFIED,
        "current_validity_state": CurrentValidityState.NOT_APPLICABLE,
        "requires_current_check": False,
        "reviewer": "independent-reviewer",
        "review_method": "passage-level-manual",
        "reviewed_at": NOW,
    }
    values.update(updates)
    return make_claim_audit(**values)


def test_verified_evidence_must_be_explicitly_selected():
    with pytest.raises(ValidationError, match="requires selected evidence"):
        audit(selected_evidence_ids=set())


def test_selected_evidence_must_come_from_candidate_set():
    with pytest.raises(ValidationError, match="subset"):
        audit(selected_evidence_ids={"ev-not-on-page"})


def test_foundational_verified_claim_can_be_source_grounded_and_not_applicable_current():
    decision = assess_claim_audit(audit())

    assert decision.source_grounded_ready is True
    assert decision.current_standard_ready is True
    assert decision.reasons == ()


def test_gap_anchor_blocks_readiness():
    record = audit(
        source_anchor_state=SourceAnchorState.GAP,
        content_fidelity_state=ContentFidelityState.VERIFIED,
    )
    decision = assess_claim_audit(record)

    assert decision.source_grounded_ready is False
    assert "source_anchor_not_pass" in decision.reasons


def test_partial_fidelity_blocks_readiness():
    record = audit(
        content_fidelity_state=ContentFidelityState.PARTIAL,
    )
    decision = assess_claim_audit(record)

    assert decision.source_grounded_ready is False
    assert "content_fidelity_not_verified" in decision.reasons


def test_time_sensitive_claim_requires_current_verified():
    record = audit(
        requires_current_check=True,
        current_validity_state=CurrentValidityState.REQUIRES_EXTERNAL_CHECK,
    )
    decision = assess_claim_audit(record)

    assert decision.source_grounded_ready is True
    assert decision.current_standard_ready is False
    assert "current_validity_not_verified" in decision.reasons


def test_current_verified_satisfies_current_check():
    record = audit(
        requires_current_check=True,
        current_validity_state=CurrentValidityState.CURRENT_VERIFIED,
    )
    decision = assess_claim_audit(record)

    assert decision.source_grounded_ready is True
    assert decision.current_standard_ready is True


def test_book_current_unchecked_is_not_current_standard():
    record = audit(
        current_validity_state=CurrentValidityState.BOOK_CURRENT_UNCHECKED,
    )
    decision = assess_claim_audit(record)

    assert decision.source_grounded_ready is True
    assert decision.current_standard_ready is False
    assert "current_standard_not_established" in decision.reasons


def test_audit_store_is_append_only_and_preserves_history(tmp_path):
    store = ClaimAuditStore(tmp_path / "audit.sqlite3")
    first = audit()
    second = audit(
        content_fidelity_state=ContentFidelityState.PARTIAL,
        reviewed_at=datetime(2026, 9, 23, 13, 0, tzinfo=timezone.utc),
        supersedes_audit_id=first.audit_id,
    )

    store.append(first)
    store.append(second)

    history = store.history(first.patch_id, first.claim_text)
    assert [item.audit_id for item in history] == [
        first.audit_id,
        second.audit_id,
    ]
    assert store.latest(first.patch_id, first.claim_text).audit_id == second.audit_id

    with pytest.raises(ValueError, match="already exists"):
        store.append(first)
