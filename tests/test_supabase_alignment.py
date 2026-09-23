from medical_learning_system.evidence_alignment import (
    AlignmentMethod,
    EvidenceStructureLink,
)
from medical_learning_system.supabase_alignment import SupabaseAlignmentStore


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.mode = "select"
        self.filters = []
        self.payload = None
        self.conflict = ""
        self.order_field = None
        self.desc = False

    def select(self, fields):
        self.mode = "select"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.desc = desc
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def upsert(self, payload, on_conflict=""):
        self.mode = "upsert"
        self.payload = payload
        self.conflict = on_conflict
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table, [])
        matched = [
            row for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        if self.mode == "select":
            result = [dict(row) for row in matched]
            if self.order_field:
                result.sort(
                    key=lambda row: row[self.order_field],
                    reverse=self.desc,
                )
            return Response(result)

        if self.mode == "delete":
            self.client.tables[self.table] = [
                row for row in rows if row not in matched
            ]
            return Response(matched)

        if self.mode == "upsert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            keys = [key for key in self.conflict.split(",") if key]
            for item in items:
                existing = next(
                    (
                        row for row in rows
                        if keys and all(row.get(key) == item.get(key) for key in keys)
                    ),
                    None,
                )
                if existing is None:
                    rows.append(dict(item))
                else:
                    existing.update(item)
            return Response(items)

        raise AssertionError(self.mode)


class Client:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return Query(self, name)


def link(evidence_id, node_id, confidence=0.95):
    return EvidenceStructureLink(
        evidence_id=evidence_id,
        source_id="costanzo",
        node_id=node_id,
        method=AlignmentMethod.HEADING_SEQUENCE,
        confidence=confidence,
    )


def test_cloud_links_preserve_many_to_many_alignment():
    client = Client()
    store = SupabaseAlignmentStore(client)
    store.replace_source(
        "costanzo",
        [
            link("ev-1", "chapter", 0.95),
            link("ev-1", "section-a", 0.95),
            link("ev-1", "section-b", 0.50),
        ],
    )

    found = store.list_evidence("ev-1")

    assert {item.node_id for item in found} == {
        "chapter",
        "section-a",
        "section-b",
    }


def test_replace_source_does_not_delete_other_source_links():
    client = Client()
    store = SupabaseAlignmentStore(client)
    store.replace_source("costanzo", [link("ev-1", "section-a")])

    other = EvidenceStructureLink(
        evidence_id="ev-2",
        source_id="guyton",
        node_id="section-x",
        method=AlignmentMethod.EXACT_HEADING,
        confidence=1.0,
    )
    store.replace_source("guyton", [other])
    store.replace_source("costanzo", [link("ev-3", "section-b")])

    rows = client.tables[SupabaseAlignmentStore.TABLE]
    assert {row["source_id"] for row in rows} == {"costanzo", "guyton"}
    assert not any(row["evidence_id"] == "ev-1" for row in rows)
