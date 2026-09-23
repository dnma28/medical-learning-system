from datetime import datetime, timedelta, timezone

import pytest

from medical_learning_system.knowledge_graph.relation_audit_ledger import (
    make_relation_audit_decision,
)
from medical_learning_system.knowledge_graph.relation_support import (
    RelationAuditMappingState,
    make_relation_audit_link,
    review_relation_audit_link,
)
from medical_learning_system.supabase_relation_audit import (
    SupabaseRelationAuditDecisionStore,
)


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client):
        self.client = client
        self.mode = "select"
        self.payload = None
        self.filters = []
        self.limit_count = None
        self.orders = []

    def select(self, fields):
        self.mode = "select"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def order(self, field):
        self.orders.append(field)
        return self

    def insert(self, payload):
        self.mode = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.mode == "insert":
            self.client.rows.append(dict(self.payload))
            return Response([dict(self.payload)])

        rows = [
            dict(row)
            for row in self.client.rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        for field in reversed(self.orders):
            rows.sort(key=lambda row: row[field])
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return Response(rows)


class Client:
    def __init__(self):
        self.rows = []

    def table(self, name):
        assert name == "mls_relation_audit_decisions"
        return Query(self)


def reviewed(state, when):
    return review_relation_audit_link(
        make_relation_audit_link("v5rel-1", "audit-1"),
        state=state,
        reviewer="reviewer",
        reviewed_at=when,
    )


def test_cloud_ledger_preserves_history():
    store = SupabaseRelationAuditDecisionStore(Client())
    first = make_relation_audit_decision(
        reviewed(RelationAuditMappingState.CONFIRMED, NOW)
    )
    store.append(first)

    second = make_relation_audit_decision(
        reviewed(
            RelationAuditMappingState.REJECTED,
            NOW + timedelta(hours=1),
        ),
        supersedes_decision_id=first.decision_id,
    )
    store.append(second)

    history = store.history(first.mapping_id)
    assert [item.decision_id for item in history] == [
        first.decision_id,
        second.decision_id,
    ]
    assert store.latest(first.mapping_id).decision_id == second.decision_id
    assert store.get(first.decision_id).state == (
        RelationAuditMappingState.CONFIRMED
    )


def test_cloud_duplicate_decision_is_rejected():
    store = SupabaseRelationAuditDecisionStore(Client())
    first = make_relation_audit_decision(
        reviewed(RelationAuditMappingState.CONFIRMED, NOW)
    )
    store.append(first)

    with pytest.raises(ValueError, match="already exists"):
        store.append(first)


def test_cloud_supersedes_must_exist():
    store = SupabaseRelationAuditDecisionStore(Client())
    record = make_relation_audit_decision(
        reviewed(RelationAuditMappingState.REJECTED, NOW),
        supersedes_decision_id="missing",
    )

    with pytest.raises(ValueError, match="does not exist"):
        store.append(record)
