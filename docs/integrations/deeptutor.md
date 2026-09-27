# DeepTutor integration

DeepTutor is an **optional, source-bounded teaching component** inside the Medical
Learning System (MLS). It is not a second curriculum, medical truth store, or learner
state system.

Pinned upstream: `HKUDS/DeepTutor v1.6.11` (Apache-2.0).

## Install

DeepTutor v1.6.11 requires Python 3.11 or newer, while MLS core remains Python >=3.10.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[deeptutor]'
python scripts/check_deeptutor.py
```

Keep textbook binaries, API keys, DeepTutor caches/indexes, and learner data outside Git.

## Runtime position

```text
Drive textbook / Source Map
        ↓
MLS retrieval + provenance/current-validity gates
        ↓
MLS Router + HỌC90 blueprint
        ↓
DeepTutorHoc90Adapter
        ↓
safe DeepTutor subset
  ├─ StudyGuidanceExtension
  └─ ReadingQuizExtension
        ↓
learner-facing interaction
        ↓
learner response
        ↓
MLS LearningEvent candidate
        ↓
Supabase Student Model / Error Graph / Skill Tree / M0–M7
```

The adapter decides whether a Router action may be delegated. The runtime executor only
receives an MLS-verified, bounded source passage. It does not search for a different
medical source.

## Safe capability mapping

| MLS action | Runtime |
| --- | --- |
| continue source spine | DeepTutor Guided Learning |
| reference coverage | DeepTutor Guided Learning |
| bounded cross-book expansion | DeepTutor Guided Learning |
| prerequisite repair | DeepTutor Guided Learning from the resolved prerequisite passage |
| optional comprehension quiz | DeepTutor Reading Quiz |
| due free retrieval | MLS native |
| observed-error closure/retest | MLS native |
| transfer/counterfactual mastery evidence | MLS native |
| source recovery | MLS native |
| current-clinical verification | MLS native |

DeepTutor's general `Deep Question` pipeline is deliberately **not** part of the HỌC90
core path. In v1.6.11 that pipeline uses the shared tool-composition surface, which can
auto-mount tools such as web fetch. HỌC90 requires the source/evidence gates to remain
under MLS control.

## Why Reading Quiz is limited to M1 evidence

The upstream Reading Quiz is multiple-choice. It verifies its answer evidence against the
provided reading context, which is useful for source-grounded comprehension, but a correct
choice is recognition rather than free recall.

Therefore:

- the learner-facing payload has `correct_choice_index` stripped;
- the answer key is retained only in the executor's private evaluator payload;
- a submitted answer becomes an append-only MLS learning-event candidate;
- the event is marked `evidence_kind=recognition`, `evidence_ceiling=M1`;
- `automatic_mastery_credit=false` always.

M2+ still requires MLS-controlled free recall, explanation, mechanism, transfer, or delayed
retrieval evidence.

## Guided Learning behavior

DeepTutor's Study Guidance extension is useful because upstream already requires the model
to work from one verified selection and to move the learner from locating evidence, to
connecting ideas, to expressing the idea in their own words without directly giving the
final answer.

MLS additionally enforces:

- source context <= 60,000 characters;
- Guided Learning selection <= 10,000 characters;
- no invented locators/citations/current standards;
- no direct learner-state or medical-truth writes;
- Router regains control after each bounded interaction.

Upstream reading prompts currently distinguish Chinese from non-Chinese rather than having
a dedicated Vietnamese prompt pack. MLS/ChatGPT remains responsible for presenting the
structured result in Vietnamese while preserving the source-grounded meaning.

## Runtime contract

`DeepTutorRuntimeExecutor` lazy-imports DeepTutor, so the MLS core can still run without
the optional dependency. It returns:

- learner-facing structured payload;
- source SHA-256 for traceability;
- non-authoritative flag;
- optional evidence ceiling;
- a private evaluator payload excluded from normal model serialization.

The executor itself never writes Supabase. A later learner response is converted into an
MLS `LearningEvent` candidate and persisted through the existing append-only learning-state
store.

## CI and upgrades

`.github/workflows/deeptutor-contract-smoke.yml` installs the exact pinned optional
dependency on Python 3.11 and checks the upstream reading-extension API without invoking an
LLM or requiring provider secrets.

Do not track DeepTutor `main` or `latest` implicitly. Upgrade the exact pin on a branch,
review upstream release/security notes, run core tests plus the contract smoke, and merge
through PR.

## Explicit non-authority rules

DeepTutor must never:

- write extraction directly to the Canonical Medical KG;
- replace Google Drive as the canonical textbook boundary;
- replace Source Maps or provenance;
- replace Supabase Student Model, Error Graph, Skill Tree, HỌC90 session/checkpoint state;
- infer mastery from exposure or reading progress;
- close an observed learner error by itself;
- award M2+ from multiple-choice recognition;
- present a time-sensitive clinical claim as current without the MLS current-validity gate.
