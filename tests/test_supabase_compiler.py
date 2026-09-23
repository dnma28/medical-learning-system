from datetime import datetime, timezone

from medical_learning_system.compiler import (
    CompilationManifest,
    CompilationStatus,
    CompilationStrategy,
)
from medical_learning_system.evidence_store import (
    EvidenceContentType,
    make_evidence_block,
)
from medical_learning_system.source_registry import (
    SourceKind,
    SourceRecord,
    SourceStatus,
)
from medical_learning_system.supabase_compiler import (
    SupabaseCompilationManifestStore,
    SupabaseEvidenceAdapter,
    SupabaseRegistryAdapter,
)
from medical_learning_system.supabase_storage import SupabaseMedicalStore


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
        self.limit_count = None
        self.order_field = None
        self.order_desc = False

    def select(self, fields):
        self.mode = "select"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def upsert(self, payload, on_conflict="", **kwargs):
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
                    reverse=self.order_desc,
                )
            if self.limit_count is not None:
                result = result[: self.limit_count]
            return Response(result)

        if self.mode == "delete":
            self.client.tables[self.table] = [
                row for row in rows if row not in matched
            ]
            return Response(matched)

        if self.mode == "upsert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            keys = [key for key in self.conflict.split(",") if key]
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
                else:
                    existing.update(item)
                    output.append(dict(existing))
            return Response(output)

        raise AssertionError(self.mode)


class Client:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return Query(self, name)


def source():
    return SourceRecord(
        source_id="source-1",
        logical_source_id="logical-1",
        provider="local",
        provider_file_id="source-1",
        title="Book.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
        kind=SourceKind.TEXTBOOK,
    )


def manifest(status=CompilationStatus.SUCCESS):
    return CompilationManifest(
        run_id="compile-1",
        source_id="source-1",
        content_sha256="a" * 64,
        strategy=CompilationStrategy.NATIVE_PDF,
        status=status,
        structure_nodes=10,
        evidence_blocks=20,
        alignment_links=30,
        grounded_evidence_blocks=18,
        needs_multimodal_enrichment=True,
        error="failed" if status == CompilationStatus.ERROR else None,
        created_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )


def test_supabase_manifest_success_round_trip():
    client = Client()
    store = SupabaseCompilationManifestStore(client)
    store.record(manifest())

    found = store.get_success(
        "source-1",
        "a" * 64,
        CompilationStrategy.NATIVE_PDF,
    )

    assert found is not None
    assert found.evidence_blocks == 20
    assert found.needs_multimodal_enrichment is True


def test_error_manifest_is_not_treated_as_success():
    client = Client()
    store = SupabaseCompilationManifestStore(client)
    store.record(manifest(CompilationStatus.ERROR))

    found = store.get_success(
        "source-1",
        "a" * 64,
        CompilationStrategy.NATIVE_PDF,
    )

    assert found is None


def test_registry_adapter_delegates_source_semantics():
    client = Client()
    medical = SupabaseMedicalStore(client)
    registry = SupabaseRegistryAdapter(medical)

    created = registry.upsert(source())
    updated = registry.set_status(
        created.record.source_id,
        SourceStatus.COMPILED,
        content_sha256="b" * 64,
    )

    assert updated.status == SourceStatus.COMPILED
    assert updated.content_sha256 == "b" * 64


def test_evidence_adapter_uses_existing_cloud_evidence_store():
    client = Client()
    medical = SupabaseMedicalStore(client)
    registry = SupabaseRegistryAdapter(medical)
    registry.upsert(source())
    adapter = SupabaseEvidenceAdapter(medical)
    block = make_evidence_block(
        source_id="source-1",
        block_index=0,
        page_index=0,
        content_type=EvidenceContentType.TEXT,
        parser="test",
        text="evidence",
    )

    adapter.replace_source("source-1", [block])

    assert medical.list_evidence("source-1")[0].evidence_id == block.evidence_id
