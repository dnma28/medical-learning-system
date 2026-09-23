from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .evidence_store import EvidenceContentType
from .parser_contract import ParsedBlock, ParsedDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def convert_with_markitdown(
    path: Path,
    *,
    allow_pdf: bool = False,
) -> ParsedDocument:
    """Convert a local non-PDF document with Microsoft MarkItDown.

    MarkItDown is intentionally an optional fallback adapter. PDF inputs are
    blocked by default because the project's native PDF / Docling pipelines
    preserve stronger page and layout provenance for medical textbooks.
    """
    path = path.resolve()
    if path.suffix.casefold() == ".pdf" and not allow_pdf:
        raise ValueError(
            "PDF sources should use native PDF or Docling by default; "
            "set allow_pdf=True only for an explicit fallback."
        )

    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError(
            "MarkItDown is not installed. Install with: "
            "pip install -e '.[markitdown]'"
        ) from exc

    result = MarkItDown().convert(str(path))
    markdown = getattr(result, "markdown", None)
    if not isinstance(markdown, str) or not markdown.strip():
        raise RuntimeError("MarkItDown returned no Markdown content.")

    return parsed_document_from_markdown(
        markdown,
        parser_version=_markitdown_version(),
    )


def parsed_document_from_markdown(
    markdown: str,
    *,
    parser_version: str | None = None,
) -> ParsedDocument:
    """Normalize Markdown into the project parser-neutral block contract.

    MarkItDown does not preserve reliable PDF page coordinates in its Markdown
    output, so blocks use page_index=0. The adapter preserves heading hierarchy
    and text blocks for downstream structure extraction.
    """
    blocks: list[ParsedBlock] = []
    paragraph: list[str] = []
    in_fence = False
    fence_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = "\n".join(paragraph).strip()
        paragraph.clear()
        if text:
            blocks.append(
                ParsedBlock(
                    block_index=len(blocks),
                    page_index=0,
                    content_type=EvidenceContentType.TEXT,
                    text=text,
                    source_type="markdown_text",
                )
            )

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.lstrip().startswith("```"):
            flush_paragraph()
            if in_fence:
                fence_lines.append(line)
                text = "\n".join(fence_lines).strip()
                if text:
                    blocks.append(
                        ParsedBlock(
                            block_index=len(blocks),
                            page_index=0,
                            content_type=EvidenceContentType.CODE,
                            text=text,
                            source_type="markdown_code",
                        )
                    )
                fence_lines = []
                in_fence = False
            else:
                in_fence = True
                fence_lines = [line]
            continue

        if in_fence:
            fence_lines.append(line)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            blocks.append(
                ParsedBlock(
                    block_index=len(blocks),
                    page_index=0,
                    content_type=EvidenceContentType.TEXT,
                    text=heading.group(2).strip(),
                    heading_level=len(heading.group(1)),
                    source_type="markdown_heading",
                )
            )
            continue

        if not line.strip():
            flush_paragraph()
            continue

        paragraph.append(line)

    if in_fence and fence_lines:
        blocks.append(
            ParsedBlock(
                block_index=len(blocks),
                page_index=0,
                content_type=EvidenceContentType.CODE,
                text="\n".join(fence_lines).strip(),
                source_type="markdown_code",
            )
        )
    else:
        flush_paragraph()

    return ParsedDocument(
        parser="markitdown",
        parser_version=parser_version,
        blocks=blocks,
    )


def _markitdown_version() -> str | None:
    try:
        return version("markitdown")
    except PackageNotFoundError:
        return None
