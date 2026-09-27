# HỌC90 START / CONTINUE runtime command

`Hoc90RuntimeService` is the backend orchestration boundary for the two learner-facing
commands:

- `HỌC 90: bắt đầu` → `Hoc90Command.START`
- `HỌC 90: tiếp tục` → `Hoc90Command.CONTINUE`

It coordinates runtime state only. It does not select a curriculum position, create medical
content, evaluate learner answers, or award mastery.

## Decision order

1. If an ACTIVE or PAUSED session exists, START and CONTINUE both resume it.
2. CONTINUE with no resumable session returns `NEEDS_BLUEPRINT`; it never invents a new
   session.
3. START without an explicitly approved curriculum position returns
   `NEEDS_CURRICULUM`.
4. START with an approved position but no ACTIVE blueprint returns `NEEDS_BLUEPRINT`.
5. START with a matching ACTIVE blueprint creates one 90-minute ACTIVE session from that
   blueprint.
6. If the active blueprint targets a different curriculum position than the explicit
   approval, bootstrap fails closed.

Structured `SourceSpineRef` values are copied exactly, including a nullable
`learning_value`. Using a source in HỌC90 never converts curriculum-neutral structure
into `CORE_MASTERY`.

## Session creation

The runtime creates only a neutral 90-minute stage skeleton:

- retrieval — 15 min
- source reasoning — 25 min
- self-explanation — 20 min
- transfer — 20 min
- consolidation — 10 min

The active blueprint supplies the source spine and learner-approved objectives. No learner
response, Error Graph node, ConceptMastery row, or SkillState row is synthesized during
bootstrap.

## CLI smoke

```bash
mls-hoc90-bootstrap continue
mls-hoc90-bootstrap start --approved-curriculum-position <position>
```

The CLI prints the bootstrap plan/session as JSON and uses the same Supabase learner-state
store as the rest of HỌC90.
