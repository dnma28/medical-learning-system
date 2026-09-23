# v0.10 — Logical Book Registry and Source Maps

## Purpose

v0.10 turns the Drive Book Registry into a machine-readable backend layer without moving textbook binaries out of Google Drive.

## Canonical identities

`data/sources/core_library.yaml` is the machine-readable logical Book Registry. It currently defines 16 logical books from the 55 direct physical files observed in `source_reparse`.

The catalog stores title/domain/edition when known, role, identity-verification state, Source Map state, filename rules, split-file rules, and safety notes. Physical Google Drive file IDs remain runtime operational metadata rather than required Git content.

## Logical vs physical source

A logical book may have:

- one full PDF;
- several split PDFs;
- a full PDF plus alternate split representations;
- suspected duplicate physical files pending byte verification.

Examples:

- Neumann: full PDF + 3 split PDFs → one logical book.
- Magee: Ortho 1–18 → one logical book; internal headings override filename chapter guesses.
- Katzung: multiple physical chunks → one logical book.

## Source Maps

`SourceMapNode` maps Part/Chapter/Section/Subsection at the logical-book level while optionally preserving a physical `source_id`, page range, and source anchor.

Physical locators are provenance-bearing data, not hints. If a node stores a page start, page end, or non-empty source anchor, it must also store the exact physical `source_id`. A page end additionally requires a page start. When the physical mapping is not verified, the locator remains unknown; the system must not infer it from filenames, neighboring nodes, or chapter numbering.

Learning-value classes:

- `CORE_MASTERY`
- `SUPPORTING`
- `REFERENCE_ONLY`
- `CURRENT_CLINICAL_CHECK`

Source coverage and learner mastery remain separate.

## Supabase

Migration `0010_logical_source_registry.sql` adds:

- `mls_logical_sources`
- `mls_source_map_nodes`

It also adds covering indexes for the four foreign keys reported by the Supabase performance advisor.

Sync the catalog with:

```bash
mls-sync-source-catalog
```

## Next

After v0.10 is stable, build complete TOC Source Maps book-by-book, then move to v0.11 multimodal figure/table/equation retrieval. Curriculum changes remain learner-approved.
