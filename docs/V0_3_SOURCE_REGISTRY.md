# v0.3 — Drive Source Registry

## Purpose

The Source Registry is the identity layer between Google Drive and the rest of
Medical Learning System.

It answers four questions before any PDF is parsed:

1. What source is this?
2. Is it new, unchanged, or changed?
3. Which logical book does a physical file belong to?
4. What processing state has already been completed?

## Why this comes before RAG expansion

The user library is expected to grow toward roughly 1000 documents. Re-parsing
or re-embedding unchanged books would waste compute and API budget.

The registry therefore performs cheap metadata change detection first.

## Two identities

A logical book can be split across several physical files.

Example:

```text
logical_source_id = neumann-kinesiology
├── source_id = neumann-kinesiology-part-1
├── source_id = neumann-kinesiology-part-2
└── source_id = neumann-kinesiology-part-3
```

The same design supports chapter-split sources such as the current Orthopedic
Assessment and Katzung source sets.

## Status lifecycle

```text
NEW
 ↓
PARSED
 ↓
INDEXED
 ↓
GRAPHED
 ↓
COMPILED
```

If provider metadata changes after processing:

```text
COMPILED → STALE
```

If a file changes before it has ever been processed, it remains `NEW`.

`ERROR` records are retriable and are not treated as canonical knowledge.

## Change detection

v0.3 uses a metadata fingerprint:

```text
provider + provider_file_id + MIME type + size + modified time
```

This is deliberately cheap.

It is **not** a cryptographic content identity. When a file is actually
downloaded for parsing, the pipeline records a byte-level SHA-256 separately.

## Storage

The operational registry uses SQLite from Python's standard library.

Reasons:

- no new database dependency;
- sufficient for ~1000 personal sources;
- transactional;
- easy to migrate later;
- compatible with a future cloud backend.

Operational state belongs under `data/local/` and is ignored by Git.

Git stores schemas, tests, and logical source manifests — not private Drive
credentials or copyrighted source files.

## Drive discovery performed for this milestone

The connected Drive currently exposes the project folder `KG v5`, including
`source_reparse`.

At the time of the v0.3 bootstrap, `source_reparse` contains 55 PDFs:

- 18 Orthopedic Assessment chapter/part PDFs;
- 19 Katzung chapter/part PDFs;
- 3 Neumann split PDFs;
- core textbooks including Guyton, Costanzo, Ganong, Kandel, Stryer,
  Moore, Junqueira, Robbins, Kisner, O'Sullivan, Bates, and Yanoff/Duker.

This confirms that physical-file identity and logical-book identity must be
separate from the beginning.

## Not in v0.3

- PDF downloading
- MinerU parsing
- TOC extraction
- embeddings
- Knowledge Graph migration
- Learning Pack compilation
- local LLM
- Neo4j

Those come only after source identity and change detection are reliable.
