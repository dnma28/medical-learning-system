from __future__ import annotations

import hashlib
import json
import sqlite3
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class EvidenceContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    EQUATION = "equation"
    CODE = "code"
    OTHER = "other"


class SourceEvidenceBlock(BaseModel):
    """Parsed source block, not a validated medical claim."""

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    structure_node_id: str | None = None
    block_index: int = Field(ge=0)
    page_index: int = Field(ge=0)
    page_label: str | None = None
    content_type: EvidenceContentType
    text: str | None = None
    asset_ref: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    parser: str = Field(min_length=1)
    parser_version: str | None = None
    content_sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def has_content(self) -> "SourceEvidenceBlock":
        if not (self.text and self.text.strip()) and not self.asset_ref:
            raise ValueError("evidence block needs text or asset_ref")
        return self

    @property
    def pdf_page(self) -> int:
        """1-based physical PDF page position."""
        return self.page_index + 1


class EvidenceSummary(BaseModel):
    source_id: str
    total: int
    text: int
    image: int
    table: int
    equation: int
    code: int
    other: int


def make_evidence_block(
    *,
    source_id: str,
    block_index: int,
    page_index: int,
    content_type: EvidenceContentType,
    parser: str,
    text: str | None = None,
    asset_ref: str | None = None,
    structure_node_id: str | None = None,
    page_label: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    parser_version: str | None = None,
) -> SourceEvidenceBlock:
    normalized_text = " ".join((text or "").split())
    content_payload = (
        f"{content_type.value}|{normalized_text}"
        if normalized_text
        else content_type.value
    )
    content_sha256 = hashlib.sha256(content_payload.encode("utf-8")).hexdigest()

    identity = "|".join(
        [
            source_id,
            str(page_index),
            str(block_index),
            content_type.value,
            content_sha256,
        ]
    )
    evidence_id = "ev-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    return SourceEvidenceBlock(
        evidence_id=evidence_id,
        source_id=source_id,
        structure_node_id=structure_node_id,
        block_index=block_index,
        page_index=page_index,
        page_label=page_label,
        content_type=content_type,
        text=text,
        asset_ref=asset_ref,
        bbox=bbox,
        parser=parser,
        parser_version=parser_version,
        content_sha256=content_sha256,
    )


class EvidenceStore:
    """SQLite store for reusable parsed source evidence."""

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
                CREATE TABLE IF NOT EXISTS evidence_blocks (
                    evidence_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    structure_node_id TEXT,
                    block_index INTEGER NOT NULL,
                    page_index INTEGER NOT NULL,
                    page_label TEXT,
                    content_type TEXT NOT NULL,
                    text TEXT,
                    asset_ref TEXT,
                    bbox_json TEXT,
                    parser TEXT NOT NULL,
                    parser_version TEXT,
                    content_sha256 TEXT NOT NULL,
                    UNIQUE (source_id, block_index)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evidence_source_page
                ON evidence_blocks(source_id, page_index, block_index)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evidence_structure
                ON evidence_blocks(source_id, structure_node_id)
                """
            )

    def replace_source(
        self,
        source_id: str,
        blocks: list[SourceEvidenceBlock],
    ) -> None:
        if any(block.source_id != source_id for block in blocks):
            raise ValueError("all evidence blocks must belong to source_id")

        ids = [block.evidence_id for block in blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence_id")

        indexes = [block.block_index for block in blocks]
        if len(indexes) != len(set(indexes)):
            raise ValueError("duplicate block_index")

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM evidence_blocks WHERE source_id = ?",
                (source_id,),
            )
            connection.executemany(
                """
                INSERT INTO evidence_blocks (
                    evidence_id, source_id, structure_node_id, block_index,
                    page_index, page_label, content_type, text, asset_ref,
                    bbox_json, parser, parser_version, content_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        block.evidence_id,
                        block.source_id,
                        block.structure_node_id,
                        block.block_index,
                        block.page_index,
                        block.page_label,
                        block.content_type.value,
                        block.text,
                        block.asset_ref,
                        json.dumps(block.bbox) if block.bbox is not None else None,
                        block.parser,
                        block.parser_version,
                        block.content_sha256,
                    )
                    for block in blocks
                ],
            )

    def list_source(self, source_id: str) -> list[SourceEvidenceBlock]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_blocks
                WHERE source_id = ?
                ORDER BY block_index
                """,
                (source_id,),
            ).fetchall()
        return [self._row_to_block(row) for row in rows]

    def list_page_range(
        self,
        source_id: str,
        page_start: int,
        page_end: int,
    ) -> list[SourceEvidenceBlock]:
        """Read evidence in a 1-based inclusive physical PDF page range."""
        if page_start < 1 or page_end < page_start:
            raise ValueError("invalid page range")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_blocks
                WHERE source_id = ?
                  AND page_index BETWEEN ? AND ?
                ORDER BY block_index
                """,
                (source_id, page_start - 1, page_end - 1),
            ).fetchall()
        return [self._row_to_block(row) for row in rows]

    def list_structure_node(
        self, source_id: str, structure_node_id: str
    ) -> list[SourceEvidenceBlock]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_blocks
                WHERE source_id = ? AND structure_node_id = ?
                ORDER BY block_index
                """,
                (source_id, structure_node_id),
            ).fetchall()
        return [self._row_to_block(row) for row in rows]

    def summarize(self, source_id: str) -> EvidenceSummary:
        counts = {content_type: 0 for content_type in EvidenceContentType}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT content_type, COUNT(*) AS count
                FROM evidence_blocks
                WHERE source_id = ?
                GROUP BY content_type
                """,
                (source_id,),
            ).fetchall()

        for row in rows:
            counts[EvidenceContentType(row["content_type"])] = row["count"]

        return EvidenceSummary(
            source_id=source_id,
            total=sum(counts.values()),
            text=counts[EvidenceContentType.TEXT],
            image=counts[EvidenceContentType.IMAGE],
            table=counts[EvidenceContentType.TABLE],
            equation=counts[EvidenceContentType.EQUATION],
            code=counts[EvidenceContentType.CODE],
            other=counts[EvidenceContentType.OTHER],
        )

    @staticmethod
    def _row_to_block(row: sqlite3.Row) -> SourceEvidenceBlock:
        bbox = json.loads(row["bbox_json"]) if row["bbox_json"] else None
        return SourceEvidenceBlock(
            evidence_id=row["evidence_id"],
            source_id=row["source_id"],
            structure_node_id=row["structure_node_id"],
            block_index=row["block_index"],
            page_index=row["page_index"],
            page_label=row["page_label"],
            content_type=EvidenceContentType(row["content_type"]),
            text=row["text"],
            asset_ref=row["asset_ref"],
            bbox=tuple(bbox) if bbox is not None else None,
            parser=row["parser"],
            parser_version=row["parser_version"],
            content_sha256=row["content_sha256"],
        )
