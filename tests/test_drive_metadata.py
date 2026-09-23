from datetime import datetime, timezone

from medical_learning_system.drive_metadata import (
    DriveFileMetadata,
    SourceAssignment,
    record_from_drive,
    stable_source_id,
    sync_drive_snapshot,
)
from medical_learning_system.source_registry import (
    SourceKind,
    SourceRegistry,
    SourceStatus,
    UpsertAction,
)


def drive_file(*, size_bytes: int = 100) -> DriveFileMetadata:
    return DriveFileMetadata(
        file_id="1-drive-file-id",
        title="Costanzo Physiology.pdf",
        mime_type="application/pdf",
        size_bytes=size_bytes,
        modified_time=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )


def assignment() -> SourceAssignment:
    return SourceAssignment(
        logical_source_id="costanzo-physiology",
        kind=SourceKind.TEXTBOOK,
        domain="physiology",
        edition="6",
    )


def test_source_id_does_not_depend_on_filename():
    first = stable_source_id("costanzo-physiology", "drive-123")
    second = stable_source_id("costanzo-physiology", "drive-123")
    assert first == second
    assert first.startswith("costanzo-physiology--")


def test_drive_metadata_becomes_source_record():
    record = record_from_drive(drive_file(), assignment())
    assert record.logical_source_id == "costanzo-physiology"
    assert record.provider_file_id == "1-drive-file-id"
    assert record.status == SourceStatus.NEW


def test_drive_snapshot_sync_is_idempotent(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.sqlite3")
    item = (drive_file(), assignment())

    created = sync_drive_snapshot(registry, [item])[0]
    unchanged = sync_drive_snapshot(registry, [item])[0]

    assert created.action == UpsertAction.CREATED
    assert unchanged.action == UpsertAction.UNCHANGED


def test_registered_source_id_survives_reclassification(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.sqlite3")
    metadata = drive_file()
    original = SourceAssignment(
        logical_source_id="temporary-classification",
        source_id="physical-source-001",
    )
    registry.upsert(record_from_drive(metadata, original))

    corrected = SourceAssignment(
        logical_source_id="costanzo-physiology",
        source_id="different-id-that-must-not-replace-the-old-one",
        kind=SourceKind.TEXTBOOK,
        domain="physiology",
    )
    result = registry.upsert(record_from_drive(metadata, corrected))

    assert result.record.source_id == "physical-source-001"
    assert result.record.logical_source_id == "costanzo-physiology"
