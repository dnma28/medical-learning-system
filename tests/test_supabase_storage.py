from datetime import datetime, timezone

from medical_learning_system.coverage import (
    CoverageState,
    StructureKind,
    StructureNode,
)
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.source_registry import (
    SourceKind,
    SourceRecord,
    SourceStatus,
    UpsertAction,
)
from medical_learning_system.supabase_storage import SupabaseMedicalStore


class Response:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = []
        self.mode = "select"
        self.payload = None
        self.select_fields = "*"
        self.order_field = None
        self.limit_count = None
        self.upsert_kwargs = {}

    def select(self, fields):
        self.mode = "select"
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def order(self, field):
        self.order_field = field
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = payload
        return self

    def upsert(self, payload, **kwargs):
        self.mode = "upsert"
        self.payload = payload
        self.upsert_kwargs = kwargs
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
                result.sort(key=lambda row: row[self.order_field])
            if self.limit_count is not None:
                result = result[: self.limit_count]
            if self.select_fields != "*":
                fields = [field.strip() for field in self.select_fields.split(",")]
                result = [{field: row.get(field) for field in fields} for row in result]
            return Response(result)

        if self.mode == "delete":
            self.client.tables[self.table] = [
                row for row in rows if row not in matched
            ]
            self._cascade_delete(matched)
            return Response(matched)

        if self.mode == "update":
            for row in matched:
                row.update(self.payload)
            return Response([dict(row) for row in matched])

        if self.mode == "upsert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            conflict = self.upsert_kwargs.get("on_conflict", "")
            keys = [key for key in conflict.split(",") if key]
            ignore = self.upsert_kwargs.get("ignore_duplicates", False)
            output = []
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
                    output.append(dict(item))
                elif ignore:
                    output.append(dict(existing))
                else:
                    existing.update(item)
                    output.append(dict(existing))
            return Response(output)

        raise AssertionError(self.mode)

    def _cascade_delete(self, deleted):
        if self.table != SupabaseMedicalStore.STRUCTURE:
            return
        coverage = self.client.tables.setdefault(SupabaseMedicalStore.COVERAGE, [])
        for row in deleted:
            coverage[:] = [
                item for item in coverage
                if not (
                    item.get("source_id") == row.get("source_id")
                    and item.get("node_id") == row.get("node_id")
                )
            ]


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeQuery(self, name)


def source(*, modified_day=22):
    return SourceRecord(
        source_id="costanzo-6e",
        logical_source_id="costanzo-physiology",
        provider="google_drive",
        provider_file_id="drive-1",
        title="Costanzo Physiology.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        modified_time=datetime(2026, 9, modified_day, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
        domain="physiology",
        edition="6",
    )


def structure():
    return [
        StructureNode(
            source_id="costanzo-6e",
            node_id="book",
            kind=StructureKind.BOOK,
            title="Costanzo",
            depth=0,
            order_index=0,
        ),
        StructureNode(
            source_id="costanzo-6e",
            node_id="ch1",
            parent_id="book",
            kind=StructureKind.CHAPTER,
            title="Chapter 1",
            depth=1,
            order_index=1,
        ),
        StructureNode(
            source_id="costanzo-6e",
            node_id="section-a",
            parent_id="ch1",
            kind=StructureKind.SECTION,
            title="Section A",
            depth=2,
            order_index=2,
        ),
    ]


def test_source_registry_semantics_are_preserved():
    store = SupabaseMedicalStore(FakeClient())

    created = store.upsert_source(source())
    assert created.action == UpsertAction.CREATED
    assert created.record.status == SourceStatus.NEW

    store.set_source_status(
        "costanzo-6e",
        SourceStatus.COMPILED,
        content_sha256="a" * 64,
    )
    unchanged = store.upsert_source(source())
    assert unchanged.action == UpsertAction.UNCHANGED
    assert unchanged.record.status == SourceStatus.COMPILED

    changed = store.upsert_source(source(modified_day=23))
    assert changed.action == UpsertAction.CHANGED
    assert changed.record.status == SourceStatus.STALE
    assert changed.record.content_sha256 is None


def test_structure_refresh_preserves_retained_coverage():
    store = SupabaseMedicalStore(FakeClient())
    store.upsert_source(source())
    store.replace_structure("costanzo-6e", structure())
    store.set_coverage("costanzo-6e", "section-a", CoverageState.MASTERED)

    refreshed = structure()[:2]
    store.replace_structure("costanzo-6e", refreshed)

    summary = store.summarize_coverage("costanzo-6e")
    assert summary.total == 1
    assert summary.not_learned == 1
    assert summary.mastered == 0


def test_structure_refresh_preserves_existing_state_for_retained_node():
    store = SupabaseMedicalStore(FakeClient())
    store.upsert_source(source())
    store.replace_structure("costanzo-6e", structure())
    store.set_coverage("costanzo-6e", "ch1", CoverageState.REVIEW)

    store.replace_structure("costanzo-6e", structure())

    summary = store.summarize_coverage("costanzo-6e")
    assert summary.review == 1
    assert summary.not_learned == 1


def test_evidence_replace_is_scoped_to_one_source():
    client = FakeClient()
    store = SupabaseMedicalStore(client)
    store.upsert_source(source())

    other = source().model_copy(
        update={
            "source_id": "guyton",
            "logical_source_id": "guyton",
            "provider_file_id": "drive-2",
            "title": "Guyton.pdf",
        }
    )
    store.upsert_source(other)

    first = make_evidence_block(
        source_id="costanzo-6e",
        block_index=0,
        page_index=0,
        content_type=EvidenceContentType.TEXT,
        parser="docling",
        text="old",
    )
    other_block = make_evidence_block(
        source_id="guyton",
        block_index=0,
        page_index=0,
        content_type=EvidenceContentType.TEXT,
        parser="docling",
        text="other",
    )
    store.replace_evidence("costanzo-6e", [first])
    store.replace_evidence("guyton", [other_block])

    refreshed = make_evidence_block(
        source_id="costanzo-6e",
        block_index=0,
        page_index=0,
        content_type=EvidenceContentType.TEXT,
        parser="docling",
        text="new",
    )
    store.replace_evidence("costanzo-6e", [refreshed])

    assert [item.text for item in store.list_evidence("costanzo-6e")] == ["new"]
    assert [item.text for item in store.list_evidence("guyton")] == ["other"]
