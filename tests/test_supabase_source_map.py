from medical_learning_system.coverage import StructureKind
from medical_learning_system.source_catalog import (
    IdentityStatus,
    SourceCatalog,
    SourceMapState,
)
from medical_learning_system.source_map import (
    LearningValue,
    LogicalSourceMap,
    SourceMapNode,
)
from medical_learning_system.supabase_source_map import SupabaseSourceMapStore


class Response:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.mode = "select"
        self.payload = None
        self.filters = []
        self.order_field = None
        self.limit_count = None
        self.conflict = []

    def select(self, _fields):
        self.mode = "select"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, field):
        self.order_field = field
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def upsert(self, payload, on_conflict=""):
        self.mode = "upsert"
        self.payload = payload
        self.conflict = [x for x in on_conflict.split(",") if x]
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = payload
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])

        if self.mode == "upsert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            for payload in payloads:
                match = next(
                    (
                        row
                        for row in rows
                        if self.conflict
                        and all(row.get(key) == payload.get(key) for key in self.conflict)
                    ),
                    None,
                )
                if match is None:
                    rows.append(dict(payload))
                else:
                    match.update(payload)
            return Response(payloads)

        matched = [
            row
            for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]

        if self.mode == "delete":
            self.client.tables[self.table] = [
                row for row in rows if row not in matched
            ]
            return Response(matched)

        if self.mode == "update":
            for row in matched:
                row.update(self.payload)
            return Response(matched)

        if self.order_field:
            matched.sort(key=lambda row: row.get(self.order_field))
        if self.limit_count is not None:
            matched = matched[: self.limit_count]
        return Response([dict(row) for row in matched])


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeQuery(self, name)


def test_catalog_sync_and_source_map_replace():
    catalog = SourceCatalog.model_validate(
        {
            "sources": [
                {
                    "logical_source_id": "costanzo-physiology",
                    "title": "Costanzo Physiology",
                    "kind": "textbook",
                    "domain": "physiology",
                    "edition": "6",
                    "role": "core physiology",
                    "identity_status": IdentityStatus.VERIFIED,
                    "source_map_state": SourceMapState.UNMAPPED,
                }
            ]
        }
    )
    client = FakeClient()
    store = SupabaseSourceMapStore(client)

    assert store.upsert_catalog(catalog) == 1
    stored = store.get_logical_source("costanzo-physiology")
    assert stored["edition"] == "6"
    assert stored["source_map_state"] == "unmapped"

    source_map = LogicalSourceMap(
        logical_source_id="costanzo-physiology",
        state=SourceMapState.TOC_MAPPED,
        nodes=[
            SourceMapNode(
                logical_source_id="costanzo-physiology",
                node_id="book",
                kind=StructureKind.BOOK,
                title="Costanzo Physiology",
                depth=0,
                order_index=0,
            ),
            SourceMapNode(
                logical_source_id="costanzo-physiology",
                node_id="ch1",
                parent_id="book",
                kind=StructureKind.CHAPTER,
                title="Chapter 1",
                depth=1,
                order_index=1,
                learning_value=LearningValue.CORE_MASTERY,
            ),
        ],
    )

    assert store.replace_source_map(source_map) == 2
    nodes = store.get_source_map("costanzo-physiology")
    assert [node["node_id"] for node in nodes] == ["book", "ch1"]
    assert (
        store.get_logical_source("costanzo-physiology")["source_map_state"]
        == "toc_mapped"
    )
