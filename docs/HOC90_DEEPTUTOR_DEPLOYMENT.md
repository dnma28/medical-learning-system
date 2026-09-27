# HỌC90 DeepTutor runtime deployment

This deployment turns the DeepTutor integration into a resumable backend bridge while
preserving MLS as the only authority for sources, learner state, and mastery.

## Runtime flow

```text
HỌC90 session + Router decision
        ↓
exact SourceSpineRef
        ↓
exact linked evidence OR explicitly supplied verified passage
        ↓
DeepTutor Guided Learning / Reading Quiz
        ↓
session PAUSED with pending interaction in checkpoint JSONB
        ↓
learner response
        ↓
interaction-id verification
        ↓
append-only mls_learning_events insert
        ↓
pending interaction cleared
        ↓
session ACTIVE again
```

No new Supabase table or migration is required. Pending DeepTutor state is kept inside
the existing backend-only `mls_learning_sessions.checkpoint` JSONB.

## Command

Install a Python 3.11 backend environment:

```bash
pip install -e '.[supabase,deeptutor]'
```

The deployed command is:

```bash
mls-hoc90-deeptutor readiness --logical-source-id guyton-hall-physiology
mls-hoc90-deeptutor prepare <session-id> --action continue_source_spine
mls-hoc90-deeptutor submit <session-id> <interaction-id> --response "..."
```

For a reading quiz:

```bash
mls-hoc90-deeptutor prepare <session-id> --action continue_source_spine --quiz
mls-hoc90-deeptutor submit <session-id> <interaction-id> \
  --question-id q_1 --choice-index 2
```

## Source policy

Automatic preparation resolves only evidence explicitly linked to the current
`source_id + source_map_node_id`. It does not semantic-search another section, guess a
page range, or substitute another book.

If no exact linked evidence exists, the command exits with `SOURCE_GAP`.

A trusted backend may instead supply a verified passage through `--source-text-file`.
This exists for ChatGPT/Drive handoff while Source Maps and evidence compilation are still
being completed. The file content is still hashed by the DeepTutor executor and the
resulting source SHA-256 is carried into the learning event.

## Session safety

Preparing an interaction:

- refuses to overwrite another pending DeepTutor interaction;
- pauses the session;
- stores public interaction data and backend-only evaluator state in the checkpoint.

Submitting a response:

- requires the exact pending interaction ID;
- appends one learning event;
- never changes M0-M7 directly;
- clears the pending interaction;
- resumes the session.

Multiple-choice Reading Quiz evidence remains recognition-only with an M1 ceiling.

## Headless model provider

The runtime can use DeepTutor's own model catalog. For server/CI deployments it can instead
inject an MLS-owned provider configuration without writing DeepTutor settings to disk:

- `MLS_DEEPTUTOR_MODEL` — model name; when absent, DeepTutor's own configured catalog is used.
- `MLS_DEEPTUTOR_API_KEY` — preferred backend-only provider credential.
- `OPENAI_API_KEY` — fallback credential.
- `MLS_DEEPTUTOR_BASE_URL` — optional OpenAI-compatible endpoint.
- `MLS_DEEPTUTOR_BINDING` — defaults to `openai`.
- `MLS_DEEPTUTOR_PROVIDER` — defaults to the binding.
- `MLS_DEEPTUTOR_API_FORMAT` — defaults to `auto`.

Do not put provider or Supabase secret keys in source control or learning prompts.

## Deployment verification

`.github/workflows/hoc90-deeptutor-runtime-readiness.yml` runs after relevant pushes to
`main`. It:

1. verifies backend Supabase secrets exist;
2. installs the pinned DeepTutor + Supabase runtime;
3. runs the upstream DeepTutor contract smoke;
4. reports whether a headless model provider is configured without printing secrets;
5. queries live HỌC90 readiness.

The readiness command reports blockers rather than fabricating missing state. Typical
blockers are:

- `no_active_blueprint`
- `no_active_or_paused_session`
- `no_evidence_blocks`
- `source_map_not_promoted`

These are project-state blockers, not reasons to weaken source provenance.
