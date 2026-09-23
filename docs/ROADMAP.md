# Roadmap

## Phase 0 — v0.1 scaffold (current)
- Stable module boundaries.
- Canonical vs candidate graph split.
- Provenance-first schema.
- RAG-Anything adapter boundary.
- Student/Error Graph separated from medical truth.

## Phase 1 — Import Knowledge Graph v5
- Map current node/edge/guard JSON into typed schema.
- Preserve existing IDs and source provenance.
- Create migration report; do not silently repair data.
- Add schema validation and duplicate-ID checks.

## Phase 2 — Multimodal ingest
- Enable RAG-Anything.
- Use MinerU as primary parser.
- Add Docling fallback/verification path.
- Persist page/chapter/figure/table provenance.
- Keep extraction outputs in candidate storage.

## Phase 3 — Biomedical normalization
- Add terminology normalization where licensing permits.
- Alias resolution and duplicate concept detection.
- Contradiction detection and cross-book evidence aggregation.

## Phase 4 — Canonical graph backend
- Move validated graph to Neo4j.
- Add graph + vector hybrid retrieval.
- Add typed relation constraints and graph tests.

## Phase 5 — Adaptive learning
- Versioned Student Model.
- Error Graph with misconception history.
- HỌC90 router consuming canonical concepts + retrieved evidence.
- Spaced retrieval scheduling and weekly assessment.

## Phase 6 — Evaluation
- Build a medical gold set.
- Evaluate retrieval relevance, faithfulness, citation completeness, and regression.
- Add RAGAS or equivalent evaluation harness.
