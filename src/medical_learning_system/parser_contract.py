from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable

from pydantic import BaseModel, Field, model_validator

from .coverage import StructureNode
from .evidence_store import (
    EvidenceContentType,
    SourceEvidenceBlock,
    make_evidence_block,
)
from .structure_extraction import HeadingCandidate, structure_from_headings


class ParsedBlock(BaseModel):
    """Parser-neutral representation of one source block."""

    block_index: int = Field(ge=0)
    page_index: int = Field(ge=0)
    content_type: EvidenceContentType
    text: str | None = None
    asset_ref: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    heading_level: int | None = Field(default=None, ge=1)
    anchor: str | None = None
    source_type: str | None = None

    @model_validator(mode="after")
    def has_content(self) -> "ParsedBlock":
        if not (self.text and self.text.strip()) and not self.asset_ref:
            raise ValueError("parsed block needs text or asset_ref")
        return self


class ParsedDocument(BaseModel):
    parser: str = Field(min_length=1)
    parser_version: str | None = None
    blocks: list[ParsedBlock]

    @model_validator(mode="after")
    def unique_block_indexes(self) -> "ParsedDocument":
        indexes = [block.block_index for block in self.blocks]
        if len(indexes) != len(set(indexes)):
            raise ValueError("duplicate block_index")
        return self


class ParsedMaterialization(BaseModel):
    structure_nodes: list[StructureNode]
    evidence_blocks: list[SourceEvidenceBlock]


def from_raganything_content(
    content_list: Iterable[Mapping[str, Any]],
    *,
    parser: str = "mineru",
    parser_version: str | None = None,
) -> ParsedDocument:
    """Normalize RAG-Anything's flat content-list contract."""
    blocks: list[ParsedBlock] = []

    for block_index, raw in enumerate(content_list):
        page_index = _nonnegative_int(raw.get("page_idx")) or 0
        raw_type = str(raw.get("type", "text")).strip().lower()
        source_type = str(raw.get("_mineru_v2_type", raw_type)).strip().lower()

        content_type = _rag_content_type(raw_type)
        text = _rag_text(raw, content_type)
        asset_ref = _optional_text(raw.get("img_path"))
        bbox = _bbox_tuple(raw.get("bbox"))

        heading_level = None
        if source_type == "title" or raw_type == "title":
            heading_level = _positive_int(raw.get("text_level", raw.get("level")))

        anchor = _optional_text(raw.get("anchor"))

        if not (text and text.strip()) and not asset_ref:
            continue

        blocks.append(
            ParsedBlock(
                block_index=block_index,
                page_index=page_index,
                content_type=content_type,
                text=text,
                asset_ref=asset_ref,
                bbox=bbox,
                heading_level=heading_level,
                anchor=anchor,
                source_type=source_type,
            )
        )

    return ParsedDocument(
        parser=parser,
        parser_version=parser_version,
        blocks=blocks,
    )


def materialize_evidence_only(
    *,
    source_id: str,
    parsed: ParsedDocument,
) -> list[SourceEvidenceBlock]:
    """Persist parser output as Evidence without inferring source hierarchy."""
    return [
        make_evidence_block(
            source_id=source_id,
            block_index=block.block_index,
            page_index=block.page_index,
            content_type=block.content_type,
            parser=parsed.parser,
            parser_version=parsed.parser_version,
            text=block.text,
            asset_ref=block.asset_ref,
            bbox=block.bbox,
        )
        for block in sorted(parsed.blocks, key=lambda item: item.block_index)
    ]


def materialize_parsed_document(
    *,
    source_id: str,
    book_title: str,
    parsed: ParsedDocument,
) -> ParsedMaterialization:
    """Create Coverage structure + reusable Evidence from one parsed document."""
    ordered = sorted(parsed.blocks, key=lambda block: block.block_index)
    headings = [
        HeadingCandidate(
            title=block.text or "",
            raw_level=block.heading_level,
            page_start=block.page_index + 1,
            anchor=block.anchor,
        )
        for block in ordered
        if block.heading_level is not None and block.text and block.text.strip()
    ]

    structure = structure_from_headings(source_id, book_title, headings)
    heading_nodes = iter(structure.nodes[1:])
    current_structure_node_id = "book"
    evidence: list[SourceEvidenceBlock] = []

    for block in ordered:
        if block.heading_level is not None and block.text and block.text.strip():
            current_structure_node_id = next(heading_nodes).node_id

        evidence.append(
            make_evidence_block(
                source_id=source_id,
                structure_node_id=current_structure_node_id,
                block_index=block.block_index,
                page_index=block.page_index,
                content_type=block.content_type,
                parser=parsed.parser,
                parser_version=parsed.parser_version,
                text=block.text,
                asset_ref=block.asset_ref,
                bbox=block.bbox,
            )
        )

    return ParsedMaterialization(
        structure_nodes=structure.nodes,
        evidence_blocks=evidence,
    )


def _rag_content_type(value: str) -> EvidenceContentType:
    if value == "image":
        return EvidenceContentType.IMAGE
    if value == "table":
        return EvidenceContentType.TABLE
    if value == "equation":
        return EvidenceContentType.EQUATION
    if value == "code":
        return EvidenceContentType.CODE
    if value == "chart":
        return EvidenceContentType.IMAGE
    if value == "text" or value == "title":
        return EvidenceContentType.TEXT
    return EvidenceContentType.OTHER


def _rag_text(
    raw: Mapping[str, Any],
    content_type: EvidenceContentType,
) -> str | None:
    direct = raw.get("text")
    if isinstance(direct, str) and direct.strip():
        return direct

    if content_type == EvidenceContentType.TABLE:
        table_body = raw.get("table_body")
        if isinstance(table_body, str) and table_body.strip():
            return table_body

    content = raw.get("content")
    if isinstance(content, str) and content.strip():
        return content
    return None


def _bbox_tuple(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return tuple(float(part) for part in value)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


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
