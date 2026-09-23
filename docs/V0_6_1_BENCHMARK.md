# v0.6.1 — Retrieval benchmark harness

## Purpose

The production embedding model is a measured decision, not an architectural
assumption.

The benchmark separates:

1. retrieval quality;
2. latency;
3. estimated provider cost.

A model that is slightly more accurate but too expensive or too slow can
therefore be compared explicitly rather than chosen subjectively.

## Gold data rule

Real benchmark labels must come from already-ingested source evidence.

A benchmark query can identify relevance at three levels:

- evidence block;
- source;
- source structure node.

Evidence can be graded, for example a directly explanatory passage may receive
a higher relevance grade than a merely related passage.

**Do not generate the real medical gold set from model memory.**

The repository currently contains only synthetic unit-test fixtures. The first
medical benchmark set will be created after the Costanzo/Guyton pilot sources
have real Evidence IDs and Coverage nodes.

## Metrics

The harness computes:

- Evidence Recall@K
- Evidence MRR@K
- Evidence nDCG@K
- Source Recall@K
- Source MRR@K
- Structure Recall@K
- Structure MRR@K
- mean latency
- p95 latency
- total estimated provider cost

Metrics whose gold labels are absent are reported as null rather than silently
substituting another target.

## Saved runs

Benchmark queries and retrieval runs use JSONL. This makes a run reproducible:
a model can be scored later without calling the model/API again.

```bash
mls-benchmark-score --queries benchmark/queries.jsonl --runs benchmark/model-a.jsonl
```

## Local embedding experiments

Sentence Transformers is optional:

```bash
pip install -e ".[embedding-local]"
```

The project currently targets Sentence Transformers 6.x, but no checkpoint is
a production dependency yet.

## Next gate

Before full-library embedding:

1. ingest a small source-backed pilot;
2. create human/source-grounded gold queries;
3. run keyword baseline;
4. run several embedding candidates;
5. compare quality, latency, storage, and cost;
6. pin one production model only if it materially beats the baseline.

Only then should an HNSW index and bulk incremental embedding job be added.
