# Parser → Coverage boundary

The Coverage Engine does not depend directly on MinerU or Docling.

Instead:

```text
MinerU / Docling
      ↓
parser-specific output
      ↓
HeadingCandidate
      ↓
validated StructureNode tree
      ↓
CoverageStore
```

## Current RAG-Anything / MinerU fields

The upstream RAG-Anything MinerU v2 adapter currently preserves:

- `page_idx` as a 0-based parser page index;
- `_mineru_v2_type = "title"` for original title blocks;
- `text_level` when MinerU provides a positive title level;
- optional `anchor`.

Medical Learning System converts `page_idx` to a 1-based physical PDF page
position for its structure layer.

## No guessed hierarchy

If parser output has title-like blocks but no usable heading level, the adapter
does not guess a chapter tree. It raises a structure extraction error so a
fallback parser or later validation path can handle the source.

## Stable node IDs

Node IDs are based on normalized heading paths, not page positions. Therefore a
heading that moves to another PDF page can retain its structure identity.

If the parser supplies an anchor, the anchor is preferred as the stable key.

## Scope limit

This adapter extracts structure only. Paragraph text, figures, tables and
equations remain evidence-layer concerns for v0.5.
