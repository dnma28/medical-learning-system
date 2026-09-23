# v0.6.5 — Evidence-to-structure alignment

## Why this layer exists

Evidence content and source structure remain separate objects. Native PDF text
does not get a fabricated `structure_node_id` during extraction.

Instead:

```text
Publisher outline ──> Coverage nodes
Native PDF blocks ──> Evidence blocks
          │                 │
          └──── aligner ─────┘
                 ↓
       EvidenceStructureLink
```

This preserves provenance and allows many-to-many relationships when a physical
page is structurally ambiguous.

## Exact alignment

For born-digital PDFs the cheapest high-confidence method is:

1. take a Coverage heading and its physical start page;
2. search native text blocks on that same page;
3. require exact Unicode/case/whitespace-normalized heading equality;
4. use the heading block's vertical position to activate that source section;
5. evidence after it follows the active hierarchy until the next exact heading.

No fuzzy matching, embedding, OCR, or LLM is used.

## Conservative fallback

If a source heading cannot be found exactly in native text, the aligner does not
guess. Evidence on affected pages receives `page_range_candidate` links to the
deepest Coverage nodes whose page ranges contain the page.

This can create multiple candidate links. That is preferable to a false exact
assignment.

## Link methods

- `exact_heading`: the evidence block is the exact source heading.
- `heading_sequence`: the block follows an exact source heading in document order.
- `page_range_candidate`: conservative fallback only.

Ancestors are retained so retrieval can be evaluated at chapter and section
levels independently.

## Storage

`EvidenceLinkStore` is SQLite-backed for the pilot. Supabase persistence is a
later migration once the alignment behavior is validated on Costanzo.
