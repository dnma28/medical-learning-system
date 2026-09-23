# v0.6.8 — Embedding benchmark candidates

The real Costanzo pilot showed that lexical retrieval is an intentionally weak
baseline for Vietnamese questions over English textbook evidence. v0.6.8
prepares a fair semantic benchmark without selecting a production winner.

## Query/document asymmetry

Some retrieval models require a different representation for queries and source
documents. The embedding interface therefore supports:

```text
encode_documents([...])
encode_query("...")
```

The legacy `encode([...])` method remains as a document-encoding alias.

The semantic evaluation layer also retains compatibility with older providers
that implement only `encode`.

## Candidate registry

`config/embedding_candidates.yaml` stores benchmark metadata and formatting
rules. The initial candidate set is deliberately heterogeneous:

- BAAI/bge-m3 — multilingual retrieval candidate.
- intfloat/multilingual-e5-large-instruct — multilingual instruct candidate.
- Alibaba-NLP/gte-multilingual-base — multilingual retrieval candidate.
- NeuML/pubmedbert-base-embeddings — English biomedical comparator.

These entries are **not a ranking** and do not imply a selected production
model.

## Fair comparison rule

Every candidate must receive:

- the same private Costanzo evidence corpus;
- the same source-grounded gold queries;
- the same K values and metrics;
- its documented query/document formatting.

The benchmark compares retrieval quality, latency and cost separately.

## Cost boundary

CI loads only YAML metadata and synthetic fake providers. It does not download
model weights.

Full-library embedding remains blocked until the private pilot supplies measured
results.
