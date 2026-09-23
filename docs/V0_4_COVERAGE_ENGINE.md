# v0.4 — Coverage Engine

## Purpose

The Coverage Engine answers a different question from the Knowledge Graph:

- **Coverage tree:** what source material exists, in what order, and has it been taught?
- **Knowledge Graph:** how do medical concepts relate across sources?

The Coverage Engine is the authority for the user's requirement that HỌC90 must
not skip chapters, sections, or subsections from the source structure.

## Core model

Each source has exactly one ordered root tree:

```text
BOOK
└── CHAPTER
    ├── SECTION
    │   ├── SUBSECTION
    │   └── SUBSECTION
    └── SECTION
```

Every node keeps:

- source ID
- stable structure node ID
- parent node
- source order
- depth
- heading
- optional page range

## Coverage state

Coverage is intentionally simpler than learner mastery:

```text
NOT_LEARNED → LEARNING → REVIEW → MASTERED
```

A future Student Model will separately track recognition, recall, explanation,
and transfer. Coverage must not be overloaded with those learner dimensions.

## Structure refresh

When a source structure is refreshed:

- retained node IDs keep their coverage state;
- removed nodes are removed with their coverage state;
- new nodes begin as NOT_LEARNED.

This is the first building block for future edition/change handling without
silently resetting all learning history.

## Storage

SQLite remains sufficient for this personal system and introduces no new
runtime dependency.

## Next v0.4 slice

The next step is not another database. It is a parser boundary that converts
MinerU/Docling TOC/heading output into these validated StructureNode records.
