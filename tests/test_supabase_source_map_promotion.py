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
        "mls_certify_source_map", "mls_promote_source_map", "mls_source_map_readiness"
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
