# v0.7 — Incremental Source Compiler

The compiler is the orchestration layer that turns a physical source into
reusable, versioned study data.

```text
physical PDF
   ↓ SHA-256
content version
   │
   ├── already successful? → SKIP
   │
   └── new/failed version
          ↓
       structure
          ↓
       evidence
          ↓
       alignment
          ↓
 Coverage / Evidence / Links
          ↓
 CompilationManifest
          ↓
       COMPILED
```

## Why content SHA-256 is the final skip key

Drive metadata is a cheap discovery/change signal, but it is not the content.
The compiler uses the exact file byte hash before deciding whether parsing is
necessary.

A filename or title change therefore does not force expensive reprocessing when
the underlying bytes are unchanged.

## Compilation manifest

Each physical source + byte hash + strategy has one manifest recording:

- source ID
- content hash
- compilation strategy
- success/error
- structure/evidence/alignment counts
- number of grounded evidence blocks
- whether multimodal enrichment is still needed
- timestamp and bounded error message

Failed versions are not treated as compiled and may be retried.

## Native baseline does not mean multimodal completeness

The first compiler strategy uses:

- publisher PDF outline for Coverage
- born-digital text blocks for Evidence
- deterministic outline-to-evidence alignment

It deliberately sets `needs_multimodal_enrichment=true`. Figures, tables,
equations and visually encoded relationships still require Docling/MinerU or a
later enrichment pass.

## Persistence safety

Parsing and alignment finish before source layers are replaced. This prevents
normal parser failures from deleting the previous usable compilation.

The current SQLite stores use separate transactions, so this is not yet a
single ACID transaction across all layers. A later cloud compiler can move the
promotion step into one Postgres transaction/RPC if production concurrency
requires it.

## CLI

```bash
mls-compile-source \
  --file /private/path/book.pdf \
  --db data/local/library.sqlite3 \
  --source-id physical-source-id \
  --logical-source-id logical-book-id \
  --title "Book title"
```

Running the command again on the exact same bytes returns
`skipped_unchanged`.
