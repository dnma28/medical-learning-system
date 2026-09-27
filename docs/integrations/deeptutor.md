# DeepTutor integration

DeepTutor is an **optional tooling layer** for the Medical Learning System. It is not the
canonical medical knowledge store and does not own learner runtime state.

Pinned upstream: `HKUDS/DeepTutor v1.6.11` (Apache-2.0).

## Install

DeepTutor requires Python 3.11 or newer.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[deeptutor]'
deeptutor --help
```

Keep DeepTutor data outside Git. Do not import textbook binaries, API keys, learner state,
or generated RAG indexes into this repository.

## Architecture boundary

Allowed uses:
- experiment with Guided Learning / question-generation behavior;
- compare retrieval and document-parsing approaches;
- use DeepTutor CLI/agent capabilities as an optional development tool;
- prototype learning UX before porting only the minimum useful behavior into MLS.

Not allowed:
- write DeepTutor extraction directly to the Canonical Medical KG;
- replace Google Drive as the canonical textbook/source-material boundary;
- replace MLS Source Maps or provenance rules;
- replace Supabase Student Model, Error Graph, Skill Tree, HỌC90 sessions/events/blueprints;
- infer mastery from exposure, reading progress, or generated explanations;
- present time-sensitive clinical output as current without the MLS current-validity gate.

DeepTutor memory/progress and MLS learner state therefore remain separate unless a future
reviewed adapter defines an explicit evidence-preserving mapping.

## Upgrade policy

Do not track DeepTutor `main` or `latest` implicitly. Upgrade the exact pin in
`pyproject.toml` on a branch, review upstream release/security notes, run MLS tests, and
merge through PR.
