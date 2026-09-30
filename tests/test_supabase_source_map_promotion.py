from types import SimpleNamespace

import pytest

from medical_learning_system.source_map_staging import StagingNode, StagingSourceMap
from medical_learning_system.supabase_source_map import SupabaseSourceMapStore


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.filters = []
        self.fields = "*"
        self.insertion = None

    def insert(self, row):
        self.insertion = row
        return self

    def select(self, fields):
        self.fields = fields
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, _key):
        return self

    def limit(self, _count):
        return self

    def execute(self):
        if self.insertion is not None:
            row = {**self.insertion, "payload_sha256": "a" * 64}
            self.client.tables.setdefault(self.table, []).append(row)
            return SimpleNamespace(data=[row])
        rows = [r for r in self.client.tables.get(self.table, [])
                if all(r.get(key) == value for key, value in self.filters)]
        if self.fields != "*":
            rows = [{key: row[key] for key in self.fields.split(",")} for row in rows]
        return SimpleNamespace(data=rows)


class FakeRpc:
    def __init__(self, client, name, payload):
        self.client, self.name, self.payload = client, name, payload

    def execute(self):
        self.client.calls.append((self.name, self.payload))
        if self.name == "mls_stage_source_map":
            version = self.payload["p_expected_latest_staging_version"] + 1
            row = {
                "logical_source_id": self.payload["p_logical_source_id"],
                "staging_version": version,
                "proposal": self.payload["p_proposal"],
                "toc_denominator": self.payload["p_toc_denominator"],
                "extraction_version": self.payload["p_extraction_version"],
                "source_manifest": self.payload["p_source_manifest"],
                "audit_metadata": self.payload["p_audit_metadata"],
                "payload_sha256": "a" * 64,
            }
            self.client.tables.setdefault("mls_source_map_staging", []).append(row)
            return SimpleNamespace(data={
                "staging_version": version,
                "payload_sha256": "a" * 64,
            })
        if self.name == "mls_claim_source_map_work":
            return SimpleNamespace(data={
                "work_key": self.payload["p_work_key"],
                "lease_token": "lease-token",
                "status": "active",
                "lease_expires_at": "2026-09-29T00:00:00+00:00",
            })
        if self.name == "mls_heartbeat_source_map_work":
            return SimpleNamespace(data="2026-09-29T00:00:00+00:00")
        if self.name in {
            "mls_complete_source_map_work",
            "mls_release_source_map_work",
        }:
            return SimpleNamespace(data=True)
        if self.name == "mls_certify_source_map":
            return SimpleNamespace(data="c" * 64)
        if self.name == "mls_promote_source_map":
            book = self.payload["p_logical_source_id"]
            stage = self.client.tables["mls_source_map_staging"][0]
            self.client.tables["mls_logical_sources"] = [{
                "logical_source_id": book, "source_map_version": 1,
                "promoted_staging_version": stage["staging_version"],
                "promoted_certificate_sha256": self.payload["p_certificate_sha256"],
            }]
            self.client.tables["mls_source_map_nodes"] = [
                {"logical_source_id": book, "node_id": node["node_id"],
                 "order_index": i}
                for i, node in enumerate(stage["proposal"])
            ]
            return SimpleNamespace(data=1)
        if self.name == "mls_source_map_readiness":
            return SimpleNamespace(data={"audited_state": "ready_for_hoc90",
                                         "ready_for_hoc90": True})
        raise AssertionError(self.name)


class FakeClient:
    def __init__(self):
        self.tables = {}
        self.calls = []

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, name, payload):
        return FakeRpc(self, name, payload)


def test_stage_certify_promote_readback_uses_one_rpc_and_preserves_null_learning_value():
    client = FakeClient()
    store = SupabaseSourceMapStore(client)
    stage = StagingSourceMap(
        logical_source_id="book", staging_version=1,
        proposal=[StagingNode(node_id="book", title="Book"),
                  StagingNode(node_id="chapter", title="Chapter", parent_id="book")],
    )
    digest = store.stage_source_map(stage)
    assert digest == "a" * 64
    assert client.tables["mls_source_map_staging"][0]["proposal"][1]["learning_value"] is None
    cert = store.certify_source_map("book", 1, digest)
    assert store.promote_source_map("book", 1, cert, expected_version=0) == 1
    assert store.get_readiness("book")["ready_for_hoc90"] is True
    assert [name for name, _ in client.calls] == [
        "mls_stage_source_map", "mls_certify_source_map",
        "mls_promote_source_map", "mls_source_map_readiness"
    ]


def test_promote_detects_mismatching_node_readback():
    client = FakeClient()
    store = SupabaseSourceMapStore(client)
    store.stage_source_map(StagingSourceMap(
        logical_source_id="book", staging_version=1,
        proposal=[StagingNode(node_id="book", title="Book")],
    ))
    original = store.get_source_map
    store.get_source_map = lambda _book: [{"node_id": "wrong"}]
    with pytest.raises(RuntimeError, match="map readback mismatch"):
        store.promote_source_map("book", 1, "c" * 64, expected_version=0)
    store.get_source_map = original



def test_stage_source_map_uses_atomic_rpc_expected_previous_version():
    client = FakeClient()
    store = SupabaseSourceMapStore(client)
    digest = store.stage_source_map(StagingSourceMap(
        logical_source_id="book",
        staging_version=3,
        proposal=[StagingNode(node_id="book", title="Book")],
    ))
    assert digest == "a" * 64
    name, payload = client.calls[0]
    assert name == "mls_stage_source_map"
    assert payload["p_expected_latest_staging_version"] == 2
    assert payload["p_logical_source_id"] == "book"


def test_source_map_work_lease_methods_use_guarded_rpcs():
    client = FakeClient()
    store = SupabaseSourceMapStore(client)
    lease = store.claim_source_map_work(
        work_key="source-map:book:b1",
        logical_source_id="book",
        batch_id="B1",
        owner_id="worker-1",
        scope_sha256="1" * 64,
        manifest_sha256="2" * 64,
        lease_seconds=900,
    )
    assert lease["lease_token"] == "lease-token"
    assert store.heartbeat_source_map_work(
        work_key="source-map:book:b1",
        lease_token="lease-token",
        lease_seconds=900,
    ).startswith("2026-")
    store.complete_source_map_work(
        work_key="source-map:book:b1",
        lease_token="lease-token",
        artifact_ref="drive:file",
        artifact_sha256="3" * 64,
    )
    store.release_source_map_work(
        work_key="source-map:book:b2",
        lease_token="lease-token",
    )
    assert [name for name, _ in client.calls] == [
        "mls_claim_source_map_work",
        "mls_heartbeat_source_map_work",
        "mls_complete_source_map_work",
        "mls_release_source_map_work",
    ]
