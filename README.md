# Medical Learning System

Source-grounded medical learning architecture for the Học nền tảng y học project.

## Architecture

1. **Canonical Medical Knowledge Graph** — validated medical knowledge only.
2. **Candidate/Evidence Graph** — extracted claims from books/RAG before validation.
3. **Learning layer (HỌC90)** — routes evidence into teaching, recall, and assessment.
4. **Student/Error Graph** — learner state stays separate from medical truth.

## Core rule

RAG/LLM extraction can retrieve and propose knowledge, but it **cannot write directly into the Canonical KG**. Every promoted medical assertion needs source provenance and validation.

## Current version: v0.2

v0.2 adds an executable first-book RAG path:

- RAG-Anything integration boundary;
- MinerU as the default parser;
- OpenAI-compatible model provider;
- local source manifests and SHA-256 fingerprints;
- `mls-ingest` for one local document;
- `mls-query` for hybrid retrieval;
- CI unit tests;
- local books, API keys, parser output, and RAG storage excluded from Git.

## Windows quick start

See `docs/V0_2_QUICKSTART.md`.

```bat
git clone https://github.com/dnma28/medical-learning-system.git
cd medical-learning-system
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev,rag]"
```

Then copy `.env.example` to `.env`, add your API key, and run:

```bat
python scripts\doctor.py
```

First-book ingestion example:

```bat
mls-ingest --manifest data/sources/costanzo-physiology-6e.example.yaml --file "C:\MedicalBooks\Costanzo Physiology 6e.pdf"
```

Query example:

```bat
mls-query "Explain the determinants of resting membrane potential."
```

## Agent tooling

The coding workflow uses Codex + the Ponytail policy in `AGENTS.md`. Optional project tooling is available for Spec Kit and OpenHarness without adding them to the medical application's runtime dependencies.

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_agent_stack.ps1
```

This installs pinned Spec Kit `v1.0.10` and OpenHarness `v0.1.9`, then initializes Spec Kit for the existing repository with the Codex integration. See `docs/AGENT_STACK.md` for workflow and verification steps.

## Important provenance limit

v0.2 can preserve source identity and local file fingerprints, and RAG-Anything's parser carries position metadata such as `page_idx`. Verified page-level evidence export into the Candidate Graph is scheduled for v0.3.

Raw copyrighted textbooks should not be committed to Git.