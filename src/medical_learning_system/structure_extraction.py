from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, Field

from .coverage import StructureKind, StructureNode, validate_structure


class StructureExtractionError(ValueError):
    pass


class HeadingCandidate(BaseModel):
    title: str = Field(min_length=1)
    raw_level: int = Field(ge=1)
    page_start: int | None = Field(default=None, ge=1)
    anchor: str | None = None


class StructureExtractionResult(BaseModel):
    nodes: list[StructureNode]
    heading_count: int
    ignored_unleveled_titles: int = 0


@dataclass
class _StackItem:
    raw_level: int
    node: StructureNode
    path_key: str


def headings_from_raganything_content(
    content_list: Iterable[Mapping[str, Any]],
) -> tuple[list[HeadingCandidate], int]:
    """Extract structural headings from RAG-Anything flat parser output."""
    headings: list[HeadingCandidate] = []
    ignored_unleveled_titles = 0

    for block in content_list:
        original_type = str(block.get("_mineru_v2_type", "")).strip().lower()
        has_level = block.get("text_level") is not None or block.get("level") is not None
        looks_like_title = original_type == "title" or str(block.get("type", "")).lower() == "title"

        if not has_level:
            if looks_like_title:
                ignored_unleveled_titles += 1
            continue

        raw_level = _positive_int(block.get("text_level", block.get("level")))
        text = str(block.get("text", "")).strip()
        if raw_level is None or not text:
            continue

        page_idx = _nonnegative_int(block.get("page_idx"))
        page_start = page_idx + 1 if page_idx is not None else None
        anchor = block.get("anchor")
        if not isinstance(anchor, str) or not anchor.strip():
            anchor = None

        headings.append(
            HeadingCandidate(
                title=text,
                raw_level=raw_level,
                page_start=page_start,
                anchor=anchor.strip() if anchor else None,
            )
        )

    return headings, ignored_unleveled_titles


def structure_from_headings(
    source_id: str,
    book_title: str,
    headings: list[HeadingCandidate],
    *,
    ignored_unleveled_titles: int = 0,
) -> StructureExtractionResult:
    if not headings:
        raise StructureExtractionError("no usable heading levels found")

    root = StructureNode(
        source_id=source_id,
        node_id="book",
        parent_id=None,
        kind=StructureKind.BOOK,
        title=book_title,
        depth=0,
        order_index=0,
    )
    nodes = [root]
    stack: list[_StackItem] = []
    sibling_counts: dict[tuple[str, str], int] = {}

    for order_index, heading in enumerate(headings, start=1):
        while stack and stack[-1].raw_level >= heading.raw_level:
            stack.pop()

        parent_node = stack[-1].node if stack else root
        parent_path = stack[-1].path_key if stack else _normalize(book_title)
        normalized_title = _normalize(heading.title)

        count_key = (parent_node.node_id, normalized_title)
        occurrence = sibling_counts.get(count_key, 0) + 1
        sibling_counts[count_key] = occurrence
        path_key = f"{parent_path}/{normalized_title}#{occurrence}"

        node_id = _node_id(source_id, heading.anchor or path_key)
        depth = parent_node.depth + 1
        kind = (
            StructureKind.CHAPTER
            if depth == 1
            else StructureKind.SECTION
            if depth == 2
            else StructureKind.SUBSECTION
        )

        node = StructureNode(
            source_id=source_id,
            node_id=node_id,
            parent_id=parent_node.node_id,
            kind=kind,
            title=heading.title,
            depth=depth,
            order_index=order_index,
            page_start=heading.page_start,
        )
        nodes.append(node)
        stack.append(_StackItem(heading.raw_level, node, path_key))

    validate_structure(source_id, nodes)
    return StructureExtractionResult(
        nodes=nodes,
        heading_count=len(headings),
        ignored_unleveled_titles=ignored_unleveled_titles,
    )


def structure_from_raganything_content(
    source_id: str,
    book_title: str,
    content_list: Iterable[Mapping[str, Any]],
) -> StructureExtractionResult:
    headings, ignored = headings_from_raganything_content(content_list)
    return structure_from_headings(
        source_id,
        book_title,
        headings,
        ignored_unleveled_titles=ignored,
    )


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _node_id(source_id: str, stable_key: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{stable_key}".encode("utf-8")).hexdigest()
    return f"struct-{digest[:16]}"


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
