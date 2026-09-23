# v0.5.1 — Normalized parser contract

Medical Learning System now treats parsers as replaceable producers.

```text
Docling ----------------┐
                        ├─> ParsedDocument
RAG-Anything / MinerU --┘
                              │
                     ┌────────┴────────┐
                     ▼                 ▼
                Coverage Tree     Evidence Store
```

## ParsedBlock

The normalized block carries only the fields the rest of the application needs:

- source order (`block_index`)
- 0-based physical PDF position (`page_index`)
- content modality
- text and/or asset reference
- optional bounding box
- optional heading level and stable anchor
- original parser block type

The core system does not need Docling classes or MinerU-specific dictionaries.

## Docling configuration

The real Docling PDF runner enables:

- OCR
- table structure
- heading hierarchy
- parsed pages required by Docling's font-style heading signal

Docling is an optional dependency:

```bash
pip install -e ".[docling]"
```

Core CI does not install Docling or download parser models. The adapter is tested
through its public structural contract using lightweight fake Docling objects.

## Current upstream baseline

The adapter was checked against Docling v2.130.0 and the current documented APIs:

- `DocumentConverter`
- `DoclingDocument.iterate_items()`
- `HeadingHierarchyOptions(enabled=True)`
- item `level`
- provenance `page_no` and `bbox`
- table `export_to_dataframe(doc=...)`

## Page convention

- Docling provenance `page_no`: 1-based
- RAG-Anything / MinerU `page_idx`: 0-based
- normalized `ParsedBlock.page_index`: always 0-based
- `SourceEvidenceBlock.pdf_page`: convenient 1-based physical PDF position

## Safety

Parser output remains extracted evidence. This layer has no Canonical KG write path.
