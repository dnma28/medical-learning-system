from __future__ import annotations

import sqlite3
import unicodedata
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .coverage import StructureNode
from .evidence_store import SourceEvidenceBlock


class AlignmentMethod(str, Enum):
    EXACT_HEADING = "exact_heading"
    HEADING_PREFIX = "heading_prefix"
    HEADING_SEQUENCE = "heading_sequence"
    PAGE_RANGE_CANDIDATE = "page_range_candidate"


class EvidenceStructureLink(BaseModel):
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    method: AlignmentMethod
    confidence: float = Field(ge=0.0, le=1.0)


def align_evidence_to_structure(
    nodes: list[StructureNode],
    evidence: list[SourceEvidenceBlock],
) -> list[EvidenceStructureLink]:
    """Align evidence to publisher structure without fuzzy or semantic guessing."""
    if not nodes:
        return []
    source_ids = {node.source_id for node in nodes}
    source_ids.update(block.source_id for block in evidence)
    if len(source_ids) != 1:
        raise ValueError("structure and evidence must belong to one source")

    by_id = {node.node_id: node for node in nodes}
    ancestors = {
        node.node_id: _ancestor_ids(node, by_id)
        for node in nodes
    }

    blocks_by_page: dict[int, list[SourceEvidenceBlock]] = {}
    for block in evidence:
        blocks_by_page.setdefault(block.pdf_page, []).append(block)
    for blocks in blocks_by_page.values():
        blocks.sort(key=_block_position)

    anchors: dict[str, tuple[SourceEvidenceBlock, AlignmentMethod]] = {}
    unresolved: list[StructureNode] = []
    for node in nodes:
        if node.parent_id is None or node.page_start is None:
            continue
        page_blocks = blocks_by_page.get(node.page_start, [])
        heading = _norm(node.title)
        exact = [
            block
            for block in page_blocks
            if block.text and _norm(block.text) == heading
        ]
        if len(exact) == 1:
            anchors[node.node_id] = (exact[0], AlignmentMethod.EXACT_HEADING)
            continue
        if len(exact) > 1:
            unresolved.append(node)
            continue

        prefix = [
            block
            for block in page_blocks
            if block.text and _norm(block.text).startswith(heading + " ")
        ]
        if len(prefix) == 1:
            anchors[node.node_id] = (prefix[0], AlignmentMethod.HEADING_PREFIX)
        else:
            unresolved.append(node)

    anchor_events = sorted(
        (
            (_document_position(block), by_id[node_id], block, method)
            for node_id, (block, method) in anchors.items()
        ),
        key=lambda item: item[0],
    )

    links: dict[tuple[str, str], EvidenceStructureLink] = {}
    for block in sorted(evidence, key=_document_position):
        position = _document_position(block)
        heading_event = next(
            (
                (node, method)
                for event_position, node, anchor_block, method in anchor_events
                if anchor_block.evidence_id == block.evidence_id
            ),
            None,
        )
        if heading_event is not None:
            exact_node, heading_method = heading_event
            _add_path_links(
                links,
                block,
                exact_node,
                ancestors,
                heading_method,
                1.0 if heading_method == AlignmentMethod.EXACT_HEADING else 0.99,
            )
            continue

        active_node = None
        for event_position, node, _, _ in anchor_events:
            if event_position <= position:
                active_node = node
            else:
                break

        if active_node is not None and not _has_unresolved_barrier(
            active_node,
            block,
            unresolved,
        ):
            _add_path_links(
                links,
                block,
                active_node,
                ancestors,
                AlignmentMethod.HEADING_SEQUENCE,
                0.95,
            )
            continue

        candidates = _deepest_page_candidates(nodes, block.pdf_page)
        for candidate in candidates:
            _add_path_links(
                links,
                block,
                candidate,
                ancestors,
                AlignmentMethod.PAGE_RANGE_CANDIDATE,
                0.5,
            )

    return sorted(
        links.values(),
        key=lambda link: (link.evidence_id, link.node_id),
    )


class EvidenceLinkStore:
    """SQLite store for evidence-to-structure alignment metadata."""

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
                CREATE TABLE IF NOT EXISTS evidence_structure_links (
                    evidence_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    method TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    PRIMARY KEY (evidence_id, node_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evidence_links_source_node
                ON evidence_structure_links(source_id, node_id)
                """
            )

    def replace_source(
        self,
        source_id: str,
        links: list[EvidenceStructureLink],
    ) -> None:
        if any(link.source_id != source_id for link in links):
            raise ValueError("all links must belong to source_id")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM evidence_structure_links WHERE source_id = ?",
                (source_id,),
            )
            connection.executemany(
                """
                INSERT INTO evidence_structure_links (
                    evidence_id, source_id, node_id, method, confidence
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        link.evidence_id,
                        link.source_id,
                        link.node_id,
                        link.method.value,
                        link.confidence,
                    )
                    for link in links
                ],
            )

    def list_evidence(self, evidence_id: str) -> list[EvidenceStructureLink]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_structure_links
                WHERE evidence_id = ?
                ORDER BY confidence DESC, node_id
                """,
                (evidence_id,),
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def list_node(
        self,
        source_id: str,
        node_id: str,
    ) -> list[EvidenceStructureLink]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_structure_links
                WHERE source_id = ? AND node_id = ?
                ORDER BY confidence DESC, evidence_id
                """,
                (source_id, node_id),
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> EvidenceStructureLink:
        return EvidenceStructureLink(
            evidence_id=row["evidence_id"],
            source_id=row["source_id"],
            node_id=row["node_id"],
            method=AlignmentMethod(row["method"]),
            confidence=row["confidence"],
        )


def _add_path_links(
    links: dict[tuple[str, str], EvidenceStructureLink],
    block: SourceEvidenceBlock,
    node: StructureNode,
    ancestors: dict[str, list[str]],
    method: AlignmentMethod,
    confidence: float,
) -> None:
    for node_id in [*ancestors[node.node_id], node.node_id]:
        key = (block.evidence_id, node_id)
        candidate = EvidenceStructureLink(
            evidence_id=block.evidence_id,
            source_id=block.source_id,
            node_id=node_id,
            method=method,
            confidence=confidence,
        )
        current = links.get(key)
        if current is None or candidate.confidence > current.confidence:
            links[key] = candidate


def _ancestor_ids(
    node: StructureNode,
    by_id: dict[str, StructureNode],
) -> list[str]:
    result: list[str] = []
    parent_id = node.parent_id
    while parent_id is not None:
        result.append(parent_id)
        parent = by_id.get(parent_id)
        parent_id = parent.parent_id if parent is not None else None
    result.reverse()
    return result


def _has_unresolved_barrier(
    active_node: StructureNode,
    block: SourceEvidenceBlock,
    unresolved: list[StructureNode],
) -> bool:
    for node in unresolved:
        if node.order_index <= active_node.order_index or node.page_start is None:
            continue
        if node.page_start < block.pdf_page:
            return True
        if node.page_start == block.pdf_page:
            return True
    return False


def _deepest_page_candidates(
    nodes: list[StructureNode],
    pdf_page: int,
) -> list[StructureNode]:
    candidates = [
        node
        for node in nodes
        if node.parent_id is not None
        and node.page_start is not None
        and node.page_end is not None
        and node.page_start <= pdf_page <= node.page_end
    ]
    if not candidates:
        return []
    deepest = max(node.depth for node in candidates)
    return [node for node in candidates if node.depth == deepest]


def _block_position(block: SourceEvidenceBlock) -> tuple[int, float, int]:
    y = block.bbox[1] if block.bbox is not None else float("inf")
    return (block.page_index, y, block.block_index)


def _document_position(block: SourceEvidenceBlock) -> tuple[int, float, int]:
    return _block_position(block)


def _norm(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
