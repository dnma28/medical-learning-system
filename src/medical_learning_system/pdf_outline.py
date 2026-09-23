from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .structure_extraction import (
    HeadingCandidate,
    StructureExtractionError,
    StructureExtractionResult,
    structure_from_headings,
)


class PdfOutlineEntry(BaseModel):
    title: str = Field(min_length=1)
    depth: int = Field(ge=0)
    page_index: int | None = Field(default=None, ge=0)


def read_pdf_outline(path: Path) -> list[PdfOutlineEntry]:
    """Read publisher-provided PDF outline/bookmarks using optional pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Native PDF outline support is not installed. "
            "Install with: pip install -e '.[pdf-native]'"
        ) from exc

    reader = PdfReader(str(path))
    outline = getattr(reader, "outline", None)
    if not outline:
        raise StructureExtractionError("PDF has no usable outline/bookmarks")

    entries: list[PdfOutlineEntry] = []

    def walk(items, depth: int = 0) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue

            title = str(getattr(item, "title", "")).strip()
            if not title:
                continue

            try:
                page_index = reader.get_destination_page_number(item)
            except Exception:
                page_index = None

            if page_index is not None and page_index < 0:
                page_index = None

            entries.append(
                PdfOutlineEntry(
                    title=title,
                    depth=depth,
                    page_index=page_index,
                )
            )

    walk(outline)
    if not entries:
        raise StructureExtractionError("PDF outline contains no titled entries")
    return entries


def structure_from_pdf_outline_entries(
    source_id: str,
    book_title: str,
    entries: list[PdfOutlineEntry],
    *,
    page_count: int | None = None,
) -> StructureExtractionResult:
    if not entries:
        raise StructureExtractionError("PDF outline is empty")

    headings = [
        HeadingCandidate(
            title=entry.title,
            raw_level=entry.depth + 1,
            page_start=(
                entry.page_index + 1 if entry.page_index is not None else None
            ),
        )
        for entry in entries
    ]
    result = structure_from_headings(source_id, book_title, headings)
    return _with_page_ranges(result, page_count)


def structure_from_pdf_outline(
    source_id: str,
    book_title: str,
    path: Path,
) -> StructureExtractionResult:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Native PDF outline support is not installed. "
            "Install with: pip install -e '.[pdf-native]'"
        ) from exc

    page_count = len(PdfReader(str(path)).pages)
    return structure_from_pdf_outline_entries(
        source_id,
        book_title,
        read_pdf_outline(path),
        page_count=page_count,
    )



def _with_page_ranges(
    result: StructureExtractionResult,
    page_count: int | None,
) -> StructureExtractionResult:
    nodes = result.nodes
    ranged = []
    for index, node in enumerate(nodes):
        if node.page_start is None or node.depth == 0:
            ranged.append(node)
            continue

        next_start = None
        for later in nodes[index + 1 :]:
            if (
                later.page_start is not None
                and later.depth <= node.depth
            ):
                next_start = later.page_start
                break

        page_end = None
        if next_start is not None:
            page_end = max(node.page_start, next_start - 1)
        elif page_count is not None:
            page_end = max(node.page_start, page_count)

        ranged.append(node.model_copy(update={"page_end": page_end}))

    return result.model_copy(update={"nodes": ranged})
