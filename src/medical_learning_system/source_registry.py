from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class SourceStatus(str, Enum):
    NEW = "new"
    PARSED = "parsed"
    INDEXED = "indexed"
    GRAPHED = "graphed"
    COMPILED = "compiled"
    STALE = "stale"
    ERROR = "error"


class SourceKind(str, Enum):
    TEXTBOOK = "textbook"
    GUIDELINE = "guideline"
    SYSTEMATIC_REVIEW = "systematic_review"
    REVIEW = "review"
    PRIMARY_STUDY = "primary_study"
    OTHER = "other"


class UpsertAction(str, Enum):
    CREATED = "created"
    UNCHANGED = "unchanged"
    CHANGED = "changed"


class SourceRecord(BaseModel):
    source_id: str = Field(min_length=1)
    logical_source_id: str = Field(min_length=1)
    provider: str = "google_drive"
    provider_file_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    size_bytes: int | None = Field(default=None, ge=0)
    modified_time: datetime
    kind: SourceKind = SourceKind.OTHER
    domain: str | None = None
    edition: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    part_index: int | None = Field(default=None, ge=1)
    status: SourceStatus = SourceStatus.NEW
    content_sha256: str | None = None

    def metadata_fingerprint(self) -> str:
        """Cheap change detector from provider metadata.

        This is not a content hash. A byte-level SHA-256 is recorded later,
        when the source is actually downloaded for parsing.
        """
        payload = "|".join(
            [
                self.provider,
                self.provider_file_id,
                self.mime_type,
                str(self.size_bytes or ""),
                self.modified_time.isoformat(),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UpsertResult:
    action: UpsertAction
    record: SourceRecord


_PROCESSED = {
    SourceStatus.PARSED,
    SourceStatus.INDEXED,
    SourceStatus.GRAPHED,
    SourceStatus.COMPILED,
}


class SourceRegistry:
    """SQLite-backed registry for source identity and processing state."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    provider TEXT NOT NULL,
                    provider_file_id TEXT NOT NULL,
                    source_id TEXT NOT NULL UNIQUE,
                    logical_source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER,
                    modified_time TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    domain TEXT,
                    edition TEXT,
                    publication_year INTEGER,
                    part_index INTEGER,
                    status TEXT NOT NULL,
                    content_sha256 TEXT,
                    metadata_fingerprint TEXT NOT NULL,
                    PRIMARY KEY (provider, provider_file_id)
                )
                """
            )

    def upsert(self, incoming: SourceRecord) -> UpsertResult:
        fingerprint = incoming.metadata_fingerprint()
        existing = self.get_by_provider_file(
            incoming.provider, incoming.provider_file_id
        )

        if existing is None:
            created = incoming.model_copy(update={"status": SourceStatus.NEW})
            self._write(created, fingerprint)
            return UpsertResult(UpsertAction.CREATED, created)

        # Physical source identity is immutable once registered. Metadata and
        # classification may be refreshed, but the stable source_id is kept.
        incoming = incoming.model_copy(update={"source_id": existing.source_id})

        if existing.metadata_fingerprint() == fingerprint:
            unchanged = incoming.model_copy(
                update={
                    "status": existing.status,
                    "content_sha256": existing.content_sha256,
                }
            )
            self._write(unchanged, fingerprint)
            return UpsertResult(UpsertAction.UNCHANGED, unchanged)

        next_status = (
            SourceStatus.STALE if existing.status in _PROCESSED else SourceStatus.NEW
        )
        changed = incoming.model_copy(
            update={"status": next_status, "content_sha256": None}
        )
        self._write(changed, fingerprint)
        return UpsertResult(UpsertAction.CHANGED, changed)

    def get_by_provider_file(
        self, provider: str, provider_file_id: str
    ) -> SourceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM sources
                WHERE provider = ? AND provider_file_id = ?
                """,
                (provider, provider_file_id),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get(self, source_id: str) -> SourceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def list_records(
        self, status: SourceStatus | None = None
    ) -> list[SourceRecord]:
        query = "SELECT * FROM sources"
        params: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY logical_source_id, part_index, source_id"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def set_status(
        self,
        source_id: str,
        status: SourceStatus,
        *,
        content_sha256: str | None = None,
    ) -> SourceRecord:
        current = self.get(source_id)
        if current is None:
            raise KeyError(source_id)

        updated = current.model_copy(
            update={
                "status": status,
                "content_sha256": (
                    content_sha256
                    if content_sha256 is not None
                    else current.content_sha256
                ),
            }
        )
        self._write(updated, updated.metadata_fingerprint())
        return updated

    def _write(self, record: SourceRecord, fingerprint: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sources (
                    provider, provider_file_id, source_id, logical_source_id,
                    title, mime_type, size_bytes, modified_time, kind, domain,
                    edition, publication_year, part_index, status,
                    content_sha256, metadata_fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_file_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    logical_source_id = excluded.logical_source_id,
                    title = excluded.title,
                    mime_type = excluded.mime_type,
                    size_bytes = excluded.size_bytes,
                    modified_time = excluded.modified_time,
                    kind = excluded.kind,
                    domain = excluded.domain,
                    edition = excluded.edition,
                    publication_year = excluded.publication_year,
                    part_index = excluded.part_index,
                    status = excluded.status,
                    content_sha256 = excluded.content_sha256,
                    metadata_fingerprint = excluded.metadata_fingerprint
                """,
                (
                    record.provider,
                    record.provider_file_id,
                    record.source_id,
                    record.logical_source_id,
                    record.title,
                    record.mime_type,
                    record.size_bytes,
                    record.modified_time.isoformat(),
                    record.kind.value,
                    record.domain,
                    record.edition,
                    record.publication_year,
                    record.part_index,
                    record.status.value,
                    record.content_sha256,
                    fingerprint,
                ),
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            source_id=row["source_id"],
            logical_source_id=row["logical_source_id"],
            provider=row["provider"],
            provider_file_id=row["provider_file_id"],
            title=row["title"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            modified_time=datetime.fromisoformat(row["modified_time"]),
            kind=SourceKind(row["kind"]),
            domain=row["domain"],
            edition=row["edition"],
            publication_year=row["publication_year"],
            part_index=row["part_index"],
            status=SourceStatus(row["status"]),
            content_sha256=row["content_sha256"],
        )
