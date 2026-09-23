from __future__ import annotations

from pathlib import Path

from .evidence_store import EvidenceContentType
from .parser_contract import ParsedBlock, ParsedDocument


def parsed_document_from_native_pdf(
    path: Path,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
) -> ParsedDocument:
    """Extract born-digital PDF text blocks without OCR or model inference.

    start_page/end_page are 1-based physical PDF positions when supplied.
    """
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "Native PDF text support is not installed. "
            "Install with: pip install -e '.[pdf-native]'"
        ) from exc

    document = fitz.open(str(path))
    first = 0 if start_page is None else start_page - 1
    last_exclusive = len(document) if end_page is None else end_page

    if first < 0 or first >= len(document):
        raise ValueError("start_page is outside the PDF")
    if last_exclusive < first + 1 or last_exclusive > len(document):
        raise ValueError("end_page is outside the PDF")

    blocks: list[ParsedBlock] = []
    block_index = 0
    for page_index in range(first, last_exclusive):
        page = document[page_index]
        for raw in page.get_text("blocks", sort=True):
            if len(raw) < 5:
                continue
            block_type = raw[6] if len(raw) > 6 else 0
            if block_type != 0:
                continue

            text = str(raw[4]).strip()
            if not text:
                continue

            blocks.append(
                ParsedBlock(
                    block_index=block_index,
                    page_index=page_index,
                    content_type=EvidenceContentType.TEXT,
                    text=text,
                    bbox=(
                        float(raw[0]),
                        float(raw[1]),
                        float(raw[2]),
                        float(raw[3]),
                    ),
                    source_type="native_pdf_text",
                )
            )
            block_index += 1

    version = getattr(fitz, "VersionBind", None)
    return ParsedDocument(
        parser="pymupdf-native",
        parser_version=str(version) if version else None,
        blocks=blocks,
    )


def native_pdf_page_count(path: Path) -> int:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "Native PDF text support is not installed. "
            "Install with: pip install -e '.[pdf-native]'"
        ) from exc

    document = fitz.open(str(path))
    return len(document)
