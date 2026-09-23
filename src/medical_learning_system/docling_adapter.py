from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .evidence_store import EvidenceContentType
from .parser_contract import ParsedBlock, ParsedDocument


def convert_pdf_with_docling(path: Path) -> ParsedDocument:
    """Convert one local PDF with Docling's structured PDF pipeline.

    Docling is an optional dependency. Imports are intentionally lazy so core
    tests and non-Docling workflows stay lightweight.
    """
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            HeadingHierarchyOptions,
            PdfPipelineOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError(
            "Docling is not installed. Install with: pip install -e '.[docling]'"
        ) from exc

    options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        heading_hierarchy_options=HeadingHierarchyOptions(enabled=True),
        generate_parsed_pages=True,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        }
    )
    result = converter.convert(str(path))
    return parsed_document_from_docling(
        result.document,
        parser_version=_docling_version(),
    )


def parsed_document_from_docling(
    document: Any,
    *,
    parser_version: str | None = None,
) -> ParsedDocument:
    """Normalize a DoclingDocument without importing Docling types.

    Duck typing keeps the application's core parser contract isolated from
    Docling's class hierarchy and keeps CI free of heavy model dependencies.
    """
    blocks: list[ParsedBlock] = []

    for block_index, pair in enumerate(document.iterate_items()):
        item, hierarchy_level = pair
        label = _label_name(item)
        content_type = _content_type(label, item)

        heading_level = None
        if label == "section_header":
            heading_level = _positive_int(getattr(item, "level", None))

        text = _item_text(item, document, content_type)
        asset_ref = None
        if content_type in {EvidenceContentType.IMAGE, EvidenceContentType.TABLE}:
            asset_ref = _self_ref(item)

        page_index, bbox = _provenance(item)
        anchor = _self_ref(item) if heading_level is not None else None

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
                source_type=label or item.__class__.__name__.casefold(),
            )
        )

    return ParsedDocument(
        parser="docling",
        parser_version=parser_version,
        blocks=blocks,
    )


def _label_name(item: Any) -> str:
    label = getattr(item, "label", None)
    if label is None:
        return ""

    value = getattr(label, "value", None)
    if isinstance(value, str):
        return value.casefold()

    name = getattr(label, "name", None)
    if isinstance(name, str):
        return name.casefold()

    return str(label).split(".")[-1].casefold()


def _content_type(label: str, item: Any) -> EvidenceContentType:
    class_name = item.__class__.__name__.casefold()

    if label in {"picture", "image"} or "picture" in class_name:
        return EvidenceContentType.IMAGE
    if label == "table" or "table" in class_name:
        return EvidenceContentType.TABLE
    if label in {"formula", "equation"}:
        return EvidenceContentType.EQUATION
    if label == "code":
        return EvidenceContentType.CODE
    return EvidenceContentType.TEXT


def _item_text(
    item: Any,
    document: Any,
    content_type: EvidenceContentType,
) -> str | None:
    text = getattr(item, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    if content_type == EvidenceContentType.TABLE:
        exporter = getattr(item, "export_to_dataframe", None)
        if callable(exporter):
            try:
                frame = exporter(doc=document)
                csv_text = frame.to_csv(index=False)
                if isinstance(csv_text, str) and csv_text.strip():
                    return csv_text
            except Exception:
                # Table text is optional here; provenance and item reference
                # are still retained for later parser-specific inspection.
                return None

    return None


def _self_ref(item: Any) -> str | None:
    value = getattr(item, "self_ref", None)
    if value is None:
        return None
    rendered = str(getattr(value, "cref", value)).strip()
    return rendered or None


def _provenance(
    item: Any,
) -> tuple[int, tuple[float, float, float, float] | None]:
    prov_items = getattr(item, "prov", None)
    if not prov_items:
        return 0, None

    prov = prov_items[0]
    page_no = _positive_int(getattr(prov, "page_no", None))
    page_index = page_no - 1 if page_no is not None else 0

    bbox = getattr(prov, "bbox", None)
    if bbox is None:
        return page_index, None

    try:
        values = (
            float(bbox.l),
            float(bbox.t),
            float(bbox.r),
            float(bbox.b),
        )
    except (AttributeError, TypeError, ValueError):
        values = None
    return page_index, values


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _docling_version() -> str | None:
    try:
        return version("docling")
    except PackageNotFoundError:
        return None
