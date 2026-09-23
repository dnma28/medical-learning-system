# v0.6.4 — Native PDF text evidence

## Low-cost ingestion path

For born-digital PDFs with usable embedded text and publisher outlines:

```text
PDF
├── publisher outline ──> Coverage Tree
└── native text blocks ─> Evidence Store
```

This path uses no OCR, LLM, vision model, embedding API, or layout model.

Docling/MinerU remain enrichment/fallback tools for:

- missing or weak native structure;
- scanned pages;
- tables whose semantics are lost in native text;
- figures;
- equations;
- difficult reading order.

## PyMuPDF evidence

The native adapter stores:

- physical page index;
- source order;
- text;
- bounding box;
- parser/version.

It intentionally labels only text. It does not claim that native PDF extraction
understands tables, diagrams, or formula semantics.

## Outline page ranges

Publisher outline nodes now receive a page range. A node ends immediately before
the next source node at the same or shallower hierarchy depth. When two headings
start on the same physical page, ranges may overlap that page rather than
pretending the PDF exposes a precise within-page semantic boundary.

This makes page-range evidence retrieval conservative.

## Pilot command

```bash
pip install -e ".[pdf-native]"

mls-pilot-ingest \
  --file "/path/to/Costanzo.pdf" \
  --source-id costanzo-physiology-6e \
  --logical-source-id costanzo-physiology \
  --title "Costanzo Physiology" \
  --gold benchmarks/costanzo_ch1_vi.jsonl
```

The output reports PDF pages, Coverage node count, Evidence block count, source
SHA-256, and whether all pilot gold anchors resolved.

## Storage

The pilot command writes only to `data/local/` by default, which is ignored by
Git. The source PDF is never copied into the repository.
