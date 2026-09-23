from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, Field

from .source_registry import (
    SourceKind,
    SourceRecord,
    SourceRegistry,
    UpsertResult,
)


class DriveFileMetadata(BaseModel):
    """Provider-neutral subset of Google Drive file metadata."""

    file_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    modified_time: datetime
    size_bytes: int | None = Field(default=None, ge=0)


class SourceAssignment(BaseModel):
    """Human/curated classification layered over raw Drive metadata."""

    logical_source_id: str = Field(min_length=1)
    source_id: str | None = None
    kind: SourceKind = SourceKind.OTHER
    domain: str | None = None
    edition: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    part_index: int | None = Field(default=None, ge=1)


def stable_source_id(logical_source_id: str, drive_file_id: str) -> str:
    """Create a stable physical source ID without depending on the filename."""
    suffix = hashlib.sha256(drive_file_id.encode("utf-8")).hexdigest()[:12]
    return f"{logical_source_id}--{suffix}"


def record_from_drive(
    metadata: DriveFileMetadata,
    assignment: SourceAssignment,
) -> SourceRecord:
    return SourceRecord(
        source_id=assignment.source_id
        or stable_source_id(assignment.logical_source_id, metadata.file_id),
        logical_source_id=assignment.logical_source_id,
        provider="google_drive",
        provider_file_id=metadata.file_id,
        title=metadata.title,
        mime_type=metadata.mime_type,
        size_bytes=metadata.size_bytes,
        modified_time=metadata.modified_time,
        kind=assignment.kind,
        domain=assignment.domain,
        edition=assignment.edition,
        publication_year=assignment.publication_year,
        part_index=assignment.part_index,
    )


def sync_drive_snapshot(
    registry: SourceRegistry,
    items: Iterable[tuple[DriveFileMetadata, SourceAssignment]],
) -> list[UpsertResult]:
    """Normalize a Drive metadata snapshot and upsert it into the registry."""
    return [
        registry.upsert(record_from_drive(metadata, assignment))
        for metadata, assignment in items
    ]
