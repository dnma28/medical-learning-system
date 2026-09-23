from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class StructureKind(str, Enum):
    BOOK = "book"
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    OTHER = "other"


class CoverageState(str, Enum):
    NOT_LEARNED = "not_learned"
    LEARNING = "learning"
    REVIEW = "review"
    MASTERED = "mastered"


class StructureNode(BaseModel):
    source_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    parent_id: str | None = None
    kind: StructureKind
    title: str = Field(min_length=1)
    depth: int = Field(ge=0)
    order_index: int = Field(ge=0)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> "StructureNode":
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be >= page_start")
        return self


class CoverageSummary(BaseModel):
    source_id: str
    total: int
    not_learned: int
    learning: int
    review: int
    mastered: int


def validate_structure(source_id: str, nodes: list[StructureNode]) -> None:
    if not nodes:
        raise ValueError("structure must contain at least one node")

    if any(node.source_id != source_id for node in nodes):
        raise ValueError("all nodes must belong to the requested source_id")

    ids = [node.node_id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate node_id in structure")

    orders = [node.order_index for node in nodes]
    if len(orders) != len(set(orders)):
        raise ValueError("duplicate order_index in structure")

    by_id = {node.node_id: node for node in nodes}
    roots = [node for node in nodes if node.parent_id is None]
    if len(roots) != 1:
        raise ValueError("structure must contain exactly one root")

    root = roots[0]
    if root.kind != StructureKind.BOOK or root.depth != 0:
        raise ValueError("root must be a book node at depth 0")

    for node in nodes:
        if node is root:
            continue
        if node.parent_id not in by_id:
            raise ValueError(f"missing parent for node {node.node_id}")
        parent = by_id[node.parent_id]
        if node.depth != parent.depth + 1:
            raise ValueError(f"invalid depth for node {node.node_id}")
        if node.order_index <= parent.order_index:
            raise ValueError(f"child must follow parent for node {node.node_id}")


class CoverageStore:
    """Ordered source structure plus learning coverage state."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS structure_nodes (
                    source_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    parent_id TEXT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    order_index INTEGER NOT NULL,
                    page_start INTEGER,
                    page_end INTEGER,
                    PRIMARY KEY (source_id, node_id),
                    UNIQUE (source_id, order_index),
                    FOREIGN KEY (source_id, parent_id)
                        REFERENCES structure_nodes(source_id, node_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS coverage (
                    source_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source_id, node_id),
                    FOREIGN KEY (source_id, node_id)
                        REFERENCES structure_nodes(source_id, node_id)
                        ON DELETE CASCADE
                );
                """
            )

    def replace_structure(
        self, source_id: str, nodes: list[StructureNode]
    ) -> None:
        validate_structure(source_id, nodes)
        ordered = sorted(nodes, key=lambda node: node.order_index)
        new_ids = {node.node_id for node in ordered}

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT node_id FROM structure_nodes WHERE source_id = ?",
                (source_id,),
            ).fetchall()
            obsolete = [row["node_id"] for row in existing if row["node_id"] not in new_ids]

            if obsolete:
                placeholders = ",".join("?" for _ in obsolete)
                connection.execute(
                    f"""
                    DELETE FROM structure_nodes
                    WHERE source_id = ? AND node_id IN ({placeholders})
                    """,
                    (source_id, *obsolete),
                )

            for node in ordered:
                connection.execute(
                    """
                    INSERT INTO structure_nodes (
                        source_id, node_id, parent_id, kind, title, depth,
                        order_index, page_start, page_end
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, node_id) DO UPDATE SET
                        parent_id = excluded.parent_id,
                        kind = excluded.kind,
                        title = excluded.title,
                        depth = excluded.depth,
                        order_index = excluded.order_index,
                        page_start = excluded.page_start,
                        page_end = excluded.page_end
                    """,
                    (
                        node.source_id,
                        node.node_id,
                        node.parent_id,
                        node.kind.value,
                        node.title,
                        node.depth,
                        node.order_index,
                        node.page_start,
                        node.page_end,
                    ),
                )
                if node.kind != StructureKind.BOOK:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO coverage (
                            source_id, node_id, state, updated_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            source_id,
                            node.node_id,
                            CoverageState.NOT_LEARNED.value,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )

    def get_structure(self, source_id: str) -> list[StructureNode]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM structure_nodes
                WHERE source_id = ?
                ORDER BY order_index
                """,
                (source_id,),
            ).fetchall()
        return [
            StructureNode(
                source_id=row["source_id"],
                node_id=row["node_id"],
                parent_id=row["parent_id"],
                kind=StructureKind(row["kind"]),
                title=row["title"],
                depth=row["depth"],
                order_index=row["order_index"],
                page_start=row["page_start"],
                page_end=row["page_end"],
            )
            for row in rows
        ]

    def set_coverage(
        self,
        source_id: str,
        node_id: str,
        state: CoverageState,
    ) -> None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT kind FROM structure_nodes
                WHERE source_id = ? AND node_id = ?
                """,
                (source_id, node_id),
            ).fetchone()
            if row is None:
                raise KeyError(node_id)
            if row["kind"] == StructureKind.BOOK.value:
                raise ValueError("book root does not have a coverage state")

            connection.execute(
                """
                UPDATE coverage
                SET state = ?, updated_at = ?
                WHERE source_id = ? AND node_id = ?
                """,
                (
                    state.value,
                    datetime.now(timezone.utc).isoformat(),
                    source_id,
                    node_id,
                ),
            )

    def summarize(self, source_id: str) -> CoverageSummary:
        counts = {state: 0 for state in CoverageState}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT state, COUNT(*) AS count
                FROM coverage
                WHERE source_id = ?
                GROUP BY state
                """,
                (source_id,),
            ).fetchall()

        for row in rows:
            counts[CoverageState(row["state"])] = row["count"]

        return CoverageSummary(
            source_id=source_id,
            total=sum(counts.values()),
            not_learned=counts[CoverageState.NOT_LEARNED],
            learning=counts[CoverageState.LEARNING],
            review=counts[CoverageState.REVIEW],
            mastered=counts[CoverageState.MASTERED],
        )
