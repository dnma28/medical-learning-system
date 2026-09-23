# v0.6.2 — Costanzo source-grounded pilot

## Why a source-anchor layer exists

Before the first real parse, benchmark evidence IDs and Coverage node IDs do not
exist yet. Inventing those IDs or relying on model memory would corrupt the
benchmark.

The pilot therefore stores only stable human-auditable anchors:

- logical source ID;
- exact chapter heading;
- exact section/subsection heading when applicable;
- optional page hint.

After Docling/MinerU creates the real Coverage tree, the resolver converts these
anchors into ordinary `BenchmarkQuery.relevant_structure_nodes`.

## Matching rule

Resolution is intentionally strict.

```text
Unicode normalization
+ case folding
+ whitespace normalization
= allowed

fuzzy matching
semantic guessing
LLM repair
= forbidden
```

Missing or ambiguous headings fail the benchmark preparation step.

## First pilot source

The first gold set is:

```text
Costanzo Physiology, 6th edition
Chapter 1 — Cellular Physiology
language of queries: Vietnamese
source headings: English
```

This deliberately tests the user's real learning pattern: asking in Vietnamese
while the source textbook is in English.

The initial anchors cover major Chapter 1 sections including body fluids, cell
membranes, membrane transport, equilibrium potentials, resting membrane
potential, action potentials, synaptic/neuromuscular transmission, skeletal
muscle, smooth muscle, and the source subheading on creation of transmembrane
concentration differences.

## Copyright boundary

The repository stores benchmark questions and short source heading names only.
It does not commit textbook passages, figures, tables, or the Drive file ID.

## Next gate

The pilot is not runnable against real evidence until one real Costanzo parse is
materialized into:

```text
CoverageStore
+
EvidenceStore
```

At that point:

1. resolve source anchors to real structure IDs;
2. run keyword retrieval baseline;
3. run selected local embedding candidates;
4. compare metrics from v0.6.1;
5. only then pin the production embedding model.
