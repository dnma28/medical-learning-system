# Medical Learning System

A source-grounded medical learning architecture with four separated layers:

1. **Canonical Medical Knowledge Graph** — validated medical knowledge only.
2. **Candidate/Evidence Graph** — extracted claims from books/RAG before validation.
3. **Learning layer (HỌC90)** — routes evidence into teaching, recall, and assessment.
4. **Student/Error Graph** — learner state stays separate from medical truth.

## Core rule

RAG/LLM extraction can retrieve and propose knowledge, but it **cannot write directly into the Canonical KG**. Every promoted medical assertion needs source provenance and validation.

## v0.1 includes

- Typed graph schema for nodes, edges, evidence, and validation state.
- Candidate -> canonical structural promotion guard.
- RAG-Anything adapter boundary.
- Minimal learning router.
- Student/Error model separated from canonical medical knowledge.
- HỌC90 session data model.
- Tests and a health-check script.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
pytest
python scripts/doctor.py
```

Enable RAG-Anything later:

```bash
pip install -e '.[rag]'
```

The official RAG-Anything package can also be installed with:

```bash
pip install "raganything[all]"
```

## Layout

```text
src/medical_learning_system/
├── knowledge_graph/
├── retrieval/
├── learning/
├── student/
└── hoc90/

data/
├── canonical/
├── candidates/
└── sources/
```

Raw copyrighted textbooks should not be committed to Git.
