# v0.6.7 — Real-source retrieval evaluation gate

## Purpose

Before selecting a production embedding model, the project must measure
retrieval quality on the same source-grounded gold set.

```text
local pilot SQLite
├── Coverage tree
├── Evidence blocks
└── EvidenceStructureLinks
        ↓
same gold queries
        ↓
┌──────────────────────┬────────────────────────┐
│ keyword FTS5 baseline│ semantic provider      │
│ no model/API cost    │ pluggable              │
└──────────────────────┴────────────────────────┘
        ↓
Recall / MRR / nDCG / source + structure metrics
```

## Keyword baseline

`LocalKeywordRetriever` uses SQLite FTS5 over already-parsed evidence. It
requires no model, network, or embedding API.

## Semantic pilot

`LocalSemanticRetriever` accepts the existing `EmbeddingProvider` protocol.
For pilot-scale evidence it uses brute-force cosine similarity, avoiding
premature vector-index tuning.

No production embedding model is chosen by this milestone.

## Private real-source command

After `mls-pilot-ingest` has created the local database:

```bash
mls-retrieval-eval \
  --db data/local/pilot.sqlite3 \
  --source-id costanzo-physiology-6e \
  --logical-source-id costanzo-physiology \
  --gold benchmarks/costanzo_ch1_vi.jsonl \
  --out-dir data/local/evaluation \
  --mode keyword
```

Semantic mode additionally requires `--embedding-model` and the optional
`embedding-local` dependency.

## Report

The summary keeps separate:

- source-grounded retrieval quality;
- latency;
- estimated cost;
- total/linked evidence count;
- alignment method counts.

Generated reports remain under `data/local/` and are not committed.

## Evaluation boundary

This milestone measures retrieval only. It does not score generated medical
answers and does not use benchmark labels as Canonical Medical KG facts.
