# v0.6 — Retrieval foundation

## Why no embedding model is pinned yet

The library target is roughly 1000 medical documents. Choosing an embedding
model before measuring medical retrieval quality can force an expensive
full-library re-embedding later.

Therefore v0.6 separates storage/retrieval from generation:

```text
Evidence Store
     │
     ├── keyword search ───────────────> usable now, no embedding cost
     │
     └── EvidenceEmbedding
              │
              ├── model A
              ├── model B
              └── future selected model
```

Embeddings from different models are never compared.

## Keyword retrieval

Postgres full-text search uses the `simple` text-search configuration. This is
deliberate: medical terms, abbreviations, Latin names and mixed-language source
material should not be aggressively English-stemmed at this stage.

Keyword retrieval gives the project a zero-embedding-cost baseline that later
semantic/hybrid retrieval must outperform.

## Semantic retrieval

`mls_match_evidence` wraps pgvector cosine distance in a Postgres RPC because
PostgREST clients do not directly expose pgvector distance operators.

Every semantic query supplies:

- query vector
- explicit embedding model name
- optional source filter
- result count

The database also checks vector dimension against the stored embedding
dimension.

## Why there is no HNSW index yet

Vector indexes should be built only after one model and dimension are selected.
The embedding table intentionally accepts several models during evaluation.

After benchmarking, a later migration will pin the production model and add a
partial HNSW cosine index for that model.

## Cost rule

`content_sha256` is stored beside every embedding. Unchanged evidence does not
need to be embedded again.

The next slice is therefore an **embedding benchmark harness**, not an automatic
paid API pipeline.
