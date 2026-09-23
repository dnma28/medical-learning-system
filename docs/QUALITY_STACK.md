# Evaluation and quality stack

The project uses evaluation tools as **measurement layers**, not as authorities that can promote medical knowledge.

## Tools

### Ragas 0.4.3

Repository: `vibrantlabsai/ragas`

Purpose in this project:

- evaluate retrieval and answer quality over curated benchmark cases;
- measure consistency across changes to chunking, embedding, retrieval, and prompting;
- generate additional evaluation cases when useful.

Install through the project extra:

```powershell
pip install -e ".[eval]"
```

Or use the convenience script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_quality_tools.ps1
```

Ragas may use LLM judges. Their scores are **evaluation signals only**. They must not automatically validate a medical assertion or write to the Canonical Medical KG.

For local privacy, Ragas documents:

```powershell
$env:RAGAS_DO_NOT_TRACK = "true"
```

### Promptfoo 0.123.1

Repository: `promptfoo/promptfoo`

Purpose in this project:

- prompt regression tests;
- model/provider comparisons;
- adversarial and red-team checks;
- CI quality gates once stable test cases exist.

The setup script installs Promptfoo locally under:

```text
.agent-tools/promptfoo/
```

when Node.js/npm is available. This keeps it out of the Python runtime dependency graph.

Example version check:

```powershell
.agent-tools\promptfoo\node_modules\.bin\promptfoo.cmd --version
```

Promptfoo results also remain quality signals. A passing LLM grader is not sufficient provenance for a medical claim.

## Installation

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_quality_tools.ps1
```

This:

1. creates `.venv` if needed;
2. installs the project with the `eval` extra, including Ragas 0.4.3;
3. installs Promptfoo 0.123.1 locally if npm is available.

## Intended evaluation hierarchy

Use progressively stronger evidence:

1. deterministic unit/integration tests;
2. retrieval metrics against curated benchmark cases;
3. Ragas/Promptfoo model-assisted metrics;
4. manual source/provenance review for medically important failures;
5. explicit validation before promotion into the Canonical Medical KG.

The project must never collapse steps 2–4 into step 5 automatically.
