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
    # A bookmark destination is a point locator. The next bookmark or the PDF
    # page count does not prove where this heading's content ends.
    return result


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


