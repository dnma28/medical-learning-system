from datetime import datetime, timedelta, timezone

import pytest

from medical_learning_system.knowledge_graph.relation_audit_ledger import (
    RelationAuditDecisionStore,
    make_relation_audit_decision,
)
from medical_learning_system.knowledge_graph.relation_support import (
    RelationAuditMappingState,
    make_relation_audit_link,
    review_relation_audit_link,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def reviewed_link(state=RelationAuditMappingState.CONFIRMED, when=NOW):
    return review_relation_audit_link(
        make_relation_audit_link("v5rel-1", "audit-1"),
        state=state,
        reviewer="reviewer",
        reviewed_at=when,
    )


def test_unreviewed_link_cannot_be_persisted_as_decision():
    with pytest.raises(ValueError, match="reviewed"):
        make_relation_audit_decision(
            make_relation_audit_link("v5rel-1", "audit-1")
        )


def test_sqlite_ledger_is_append_only_and_keeps_history(tmp_path):
    store = RelationAuditDecisionStore(tmp_path / "relation.sqlite3")
    first = make_relation_audit_decision(reviewed_link())
    store.append(first)

    correction_link = reviewed_link(
        RelationAuditMappingState.REJECTED,
        NOW + timedelta(hours=1),
    )
    correction = make_relation_audit_decision(
        correction_link,
        supersedes_decision_id=first.decision_id,
    )
    store.append(correction)

    history = store.history(first.mapping_id)
    assert [item.state for item in history] == [
        RelationAuditMappingState.CONFIRMED,
        RelationAuditMappingState.REJECTED,
    ]
    assert store.latest(first.mapping_id).decision_id == correction.decision_id
    assert store.get(first.decision_id).state == (
        RelationAuditMappingState.CONFIRMED
    )


def test_duplicate_decision_id_is_rejected(tmp_path):
    store = RelationAuditDecisionStore(tmp_path / "relation.sqlite3")
    record = make_relation_audit_decision(reviewed_link())
    store.append(record)

    with pytest.raises(ValueError, match="already exists"):
        store.append(record)


def test_supersedes_must_reference_same_mapping(tmp_path):
    store = RelationAuditDecisionStore(tmp_path / "relation.sqlite3")
    first = make_relation_audit_decision(reviewed_link())
    store.append(first)

    other = review_relation_audit_link(
        make_relation_audit_link("v5rel-2", "audit-1"),
        state=RelationAuditMappingState.REJECTED,
        reviewer="reviewer",
        reviewed_at=NOW + timedelta(hours=1),
    )
    correction = make_relation_audit_decision(
        other,
        supersedes_decision_id=first.decision_id,
    )

    with pytest.raises(ValueError, match="different mapping"):
        store.append(correction)
