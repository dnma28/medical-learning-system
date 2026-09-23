from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from ..coverage import StructureKind, StructureNode
from .benchmark import BenchmarkQuery


class GoldResolutionError(ValueError):
    pass


class SourceHeadingAnchor(BaseModel):
    logical_source_id: str = Field(min_length=1)
    chapter_title: str = Field(min_length=1)
    heading_title: str | None = None
    page_hint: int | None = Field(default=None, ge=1)


class SourceGroundedBenchmarkItem(BaseModel):
    query_id: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    language: str | None = None
    anchors: list[SourceHeadingAnchor] = Field(min_length=1)
    tags: set[str] = Field(default_factory=set)
    provenance_note: str | None = None

    @model_validator(mode="after")
    def anchors_use_one_logical_source(self) -> "SourceGroundedBenchmarkItem":
        logical_ids = {anchor.logical_source_id for anchor in self.anchors}
        if len(logical_ids) != 1:
            raise ValueError("one benchmark item must target one logical source")
        return self


def load_source_gold_jsonl(path: Path) -> list[SourceGroundedBenchmarkItem]:
    return [
        SourceGroundedBenchmarkItem.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def resolve_source_gold(
    items: list[SourceGroundedBenchmarkItem],
    *,
    logical_source_id: str,
    physical_source_id: str,
    nodes: list[StructureNode],
) -> list[BenchmarkQuery]:
    """Resolve source-heading gold anchors only after real structure extraction.

    Matching is exact after Unicode/case/whitespace normalization. Missing or
    ambiguous headings are errors; the resolver never fuzzy-matches or guesses.
    """
    if not nodes:
        raise GoldResolutionError("source structure is empty")
    if any(node.source_id != physical_source_id for node in nodes):
        raise GoldResolutionError("structure contains a different physical source")

    by_id = {node.node_id: node for node in nodes}
    children: dict[str, list[StructureNode]] = {}
    for node in nodes:
        if node.parent_id is not None:
            children.setdefault(node.parent_id, []).append(node)

    resolved: list[BenchmarkQuery] = []
    for item in items:
        structure_ids: set[str] = set()

        for anchor in item.anchors:
            if anchor.logical_source_id != logical_source_id:
                raise GoldResolutionError(
                    f"{item.query_id}: anchor logical source does not match "
                    f"{logical_source_id}"
                )

            chapters = [
                node
                for node in nodes
                if node.kind == StructureKind.CHAPTER
                and _chapter_norm(node.title) == _chapter_norm(anchor.chapter_title)
            ]
            if len(chapters) != 1:
                raise GoldResolutionError(
                    f"{item.query_id}: expected exactly one chapter "
                    f"{anchor.chapter_title!r}, found {len(chapters)}"
                )
            chapter = chapters[0]

            if anchor.heading_title is None:
                structure_ids.add(chapter.node_id)
                continue

            descendants = _descendants(chapter.node_id, children)
            matches = [
                node
                for node in descendants
                if _norm(node.title) == _norm(anchor.heading_title)
            ]
            if len(matches) != 1:
                raise GoldResolutionError(
                    f"{item.query_id}: expected exactly one heading "
                    f"{anchor.heading_title!r} under {anchor.chapter_title!r}, "
                    f"found {len(matches)}"
                )
            structure_ids.add(matches[0].node_id)

        resolved.append(
            BenchmarkQuery(
                query_id=item.query_id,
                query_text=item.query_text,
                language=item.language,
                relevant_sources={physical_source_id},
                relevant_structure_nodes=structure_ids,
                tags=item.tags,
            )
        )

    return resolved


def _descendants(
    parent_id: str,
    children: dict[str, list[StructureNode]],
) -> list[StructureNode]:
    result: list[StructureNode] = []
    stack = list(reversed(children.get(parent_id, [])))
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(reversed(children.get(node.node_id, [])))
    return result


def _norm(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


_CHAPTER_PREFIX = re.compile(
    r"^(?:chapter\\s+)?(?:\\d+|[ivxlcdm]+)\\s*[:.\\-–—]?\\s+",
    re.IGNORECASE,
)


def _chapter_norm(value: str) -> str:
    normalized = _norm(value)
    return _CHAPTER_PREFIX.sub("", normalized)
