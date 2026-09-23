from datetime import datetime, timezone

import pytest

from medical_learning_system.knowledge_graph.claim_audit import (
    ContentFidelityState,
    CurrentValidityState,
    SourceAnchorState,
    make_claim_audit,
)
from medical_learning_system.supabase_claim_audit import (
    SupabaseClaimAuditStore,
)


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.mode = "select"
        self.payload = None
        self.filters = []
        self.orders = []
        self.limit_count = None

    def select(self, fields):
        self.mode = "select"
        return self

    def insert(self, payload):
        self.mode = "insert"
        self.payload = payload
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, field, **kwargs):
        self.orders.append((field, kwargs.get("desc", False)))
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        if self.mode == "insert":
            if any(row["audit_id"] == self.payload["audit_id"] for row in rows):
                raise RuntimeError("duplicate key")
            rows.append(dict(self.payload))
            return Response([dict(self.payload)])

        matched = [
            dict(row)
            for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        for field, desc in reversed(self.orders):
            matched.sort(key=lambda row: row[field], reverse=desc)
        if self.limit_count is not None:
            matched = matched[: self.limit_count]
        return Response(matched)


class Client:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return Query(self, name)


def record(*, hour=12, supersedes=None):
    return make_claim_audit(
        patch_id="foundation.homeostasis.v1",
        claim_text="homeostasis is dynamic",
        source_anchor_id="sa-b04",
        source_anchor_state=SourceAnchorState.PASS,
        evidence_candidate_ids={"ev-1", "ev-2"},
        selected_evidence_ids={"ev-1"},
        content_fidelity_state=ContentFidelityState.VERIFIED,
        current_validity_state=CurrentValidityState.NOT_APPLICABLE,
        requires_current_check=False,
        reviewer="reviewer",
        review_method="passage-level-manual",
        reviewed_at=datetime(2026, 9, 23, hour, tzinfo=timezone.utc),
        supersedes_audit_id=supersedes,
    )


def test_cloud_audit_round_trip():
    store = SupabaseClaimAuditStore(Client())
    item = record()

    store.append(item)
    loaded = store.get(item.audit_id)

    assert loaded == item


def test_cloud_audit_history_is_ordered_and_latest_is_last():
    store = SupabaseClaimAuditStore(Client())
    first = record(hour=12)
    second = record(hour=13, supersedes=first.audit_id)

    store.append(second)
    store.append(first)

    history = store.history(first.patch_id, first.claim_text)
    assert [item.audit_id for item in history] == [
        first.audit_id,
        second.audit_id,
    ]
    assert store.latest(first.patch_id, first.claim_text) == second


def test_cloud_store_rejects_duplicate_audit_id_before_insert():
    store = SupabaseClaimAuditStore(Client())
    item = record()
    store.append(item)

    with pytest.raises(ValueError, match="already exists"):
        store.append(item)
