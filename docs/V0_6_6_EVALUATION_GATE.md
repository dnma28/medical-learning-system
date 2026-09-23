# v0.6.6 — Real-source retrieval evaluation gate

This milestone blocks full-library embedding until retrieval quality is measured
against source-grounded gold targets.

## Private real-source flow

```text
private PDF
   ↓
pilot ingestion
   ↓
Coverage + Evidence + alignment links
   ↓
source-heading gold anchors
   ↓ strict resolution
resolved BenchmarkQuery set
   ↓
┌──────────────────┬──────────────────────┐
│ keyword baseline │ semantic provider(s) │
└──────────────────┴──────────────────────┘
   ↓
same metrics / same gold set
```

Only metrics and evidence IDs are written to evaluation output. Source passages
are not copied into Git.

## Grounding gate

An evidence block enters the benchmark corpus only when it has at least one
explicit EvidenceStructureLink.

A benchmark heading target must also have at least one evidence link. If it does
not, evaluation fails instead of inventing relevance labels.

## Alignment report

The report includes:

- total/text evidence counts
- grounded vs ungrounded text blocks
- exact/prefix/sequence alignment counts
- page-range-candidate-only count

This makes retrieval scores interpretable: a low retrieval score should not be
confused with incomplete evidence-to-structure alignment.

## Keyword baseline

The local keyword retriever is deterministic token overlap and has no API/model
cost. It is intentionally simple. Its purpose is to establish a minimum
cross-lingual baseline before semantic embeddings are adopted.

## Semantic benchmark

SemanticCorpusRetriever depends only on the EmbeddingProvider protocol. The
optional SentenceTransformerProvider can be selected from the CLI for a small,
private pilot corpus.

No production model is selected by this milestone.

## Example private run

```bash
mls-evaluate-retrieval \
  --db data/local/costanzo.sqlite3 \
  --gold benchmarks/costanzo_ch1_vi.jsonl \
  --source-id costanzo-local \
  --logical-source-id costanzo-physiology \
  --k 10
```

To test a local embedding model, add:

```bash
--semantic-model <sentence-transformers-model>
```

Do not run the full ~1000-document embedding job until this gate has produced a
representative result.
