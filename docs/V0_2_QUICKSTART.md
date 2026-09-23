# v0.2 Quick Start — First real PDF

The goal of v0.2 is intentionally narrow:

> Ingest one local medical textbook into RAG-Anything and run one hybrid query.

The PDF remains on the local computer and is **not** committed to GitHub.

## 1. Clone the repository

```bash
git clone https://github.com/dnma28/medical-learning-system.git
cd medical-learning-system
```

## 2. Create a virtual environment

### Windows CMD

```bat
python -m venv .venv
.venv\Scripts\activate
```

## 3. Install the project

```bat
python -m pip install --upgrade pip
pip install -e ".[dev,rag]"
```

This installs RAG-Anything with its optional Python dependencies.

## 4. Create your local .env

Copy `.env.example` to `.env`, then set:

```text
OPENAI_API_KEY=your_key_here
```

Never commit `.env`.

## 5. Check installation

```bat
python scripts\doctor.py
mineru --version
pytest
```

## 6. Keep the textbook local

Example:

```text
C:\MedicalBooks\Costanzo Physiology 6e.pdf
```

Do not copy the book into the Git repository.

## 7. Ingest Costanzo

```bat
mls-ingest --manifest data/sources/costanzo-physiology-6e.example.yaml --file "C:\MedicalBooks\Costanzo Physiology 6e.pdf"
```

First use may download parser models and can take substantially longer than later runs.

## 8. Run the first query

```bat
mls-query "Explain the determinants of resting membrane potential."
```

The v0.2 success condition is that the system processes the PDF and returns a relevant answer from the indexed source.

## Provenance limitation in v0.2

RAG-Anything preserves parser position metadata such as `page_idx`, but this first executable milestone does not yet expose verified page-level citations in the final query output.

Therefore:

- retrieved/generated answers remain **RAG evidence**, not canonical truth;
- no RAG answer is automatically promoted into the Canonical Medical KG;
- page-level evidence export is a v0.3 task.