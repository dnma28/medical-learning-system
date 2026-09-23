# v0.6.3 — Native PDF outline-first extraction

## Finding from the first real source

The current Costanzo Physiology 6e PDF was inspected before running an ML
parser.

Observed:

- 493 physical PDF pages;
- not encrypted;
- 899 publisher/bookmark outline entries;
- nested outline depth reaches detailed cellular-physiology subsections.

For example, the native outline already exposes the hierarchy from Chapter 1
through membrane transport, equilibrium potentials, action potentials,
synaptic transmission, and muscle subsections.

This means the project should not pay an ML parser to rediscover structure that
the source already provides.

## New structure priority

```text
PDF source
   │
   ├─ usable native outline? ── YES ──> Coverage Tree
   │
   └─ NO
       ↓
     Docling heading hierarchy
       ↓ insufficient
     MinerU / RAG-Anything heading levels
```

The parser used for Evidence extraction can still be Docling or MinerU. The
important change is that **Coverage authority prefers source-native structure**.

## Why this is better

- no model/API call;
- very fast;
- authored by publisher/source rather than inferred from visual styling;
- preserves deep subsection hierarchy;
- page destinations provide physical PDF page provenance;
- stable path-based node IDs survive page movement.

## Optional dependency

```bash
pip install -e ".[pdf-native]"
```

The dependency is lazy; core CI does not require PDF parsing.

## Fallback rule

A fallback parser may fill a missing structure when the native outline is absent
or unusable. It must not silently replace a validated native outline for the
same source.

## Costanzo pilot

The real source inspection showed this approach is sufficient to build the
Chapter 1 Coverage tree without Docling. Docling/MinerU remains necessary for
paragraph/table/figure/equation Evidence extraction.
