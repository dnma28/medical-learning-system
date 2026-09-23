from datetime import datetime, timezone

from medical_learning_system.source_registry import (
    SourceKind,
    SourceRecord,
    SourceRegistry,
    SourceStatus,
    UpsertAction,
)


def record(*, modified_time: datetime, size_bytes: int = 100) -> SourceRecord:
    return SourceRecord(
        source_id="costanzo-physiology-6e",
        logical_source_id="costanzo-physiology",
        provider_file_id="drive-file-1",
        title="Costanzo Physiology 6e.pdf",
        mime_type="application/pdf",
        size_bytes=size_bytes,
        modified_time=modified_time,
        kind=SourceKind.TEXTBOOK,
        domain="physiology",
        edition="6",
    )


def test_new_source_is_created(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.sqlite3")
    result = registry.upsert(
        record(modified_time=datetime(2026, 9, 22, tzinfo=timezone.utc))
    )
    assert result.action == UpsertAction.CREATED
    assert result.record.status == SourceStatus.NEW


def test_unchanged_source_is_idempotent(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.sqlite3")
    source = record(modified_time=datetime(2026, 9, 22, tzinfo=timezone.utc))

    registry.upsert(source)
    registry.set_status(
        source.source_id,
        SourceStatus.INDEXED,
        content_sha256="a" * 64,
    )

    result = registry.upsert(source)
    assert result.action == UpsertAction.UNCHANGED
    assert result.record.status == SourceStatus.INDEXED
    assert result.record.content_sha256 == "a" * 64


def test_changed_processed_source_becomes_stale(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.sqlite3")
    first = record(modified_time=datetime(2026, 9, 22, tzinfo=timezone.utc))
    registry.upsert(first)
    registry.set_status(
        first.source_id,
        SourceStatus.COMPILED,
        content_sha256="b" * 64,
    )

    changed = record(
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
        size_bytes=101,
    )
    result = registry.upsert(changed)

    assert result.action == UpsertAction.CHANGED
    assert result.record.status == SourceStatus.STALE
    assert result.record.content_sha256 is None


def test_changed_unprocessed_source_stays_new(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.sqlite3")
    registry.upsert(
        record(modified_time=datetime(2026, 9, 22, tzinfo=timezone.utc))
    )

    result = registry.upsert(
        record(modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc))
    )

    assert result.action == UpsertAction.CHANGED
    assert result.record.status == SourceStatus.NEW
