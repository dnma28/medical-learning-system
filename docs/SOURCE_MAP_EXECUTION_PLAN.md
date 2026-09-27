# Source Map execution plan — stable serial closure

This plan is the operational companion to milestone #97. It reduces repeated full-project restarts by using one durable work queue, immutable source-evidence packets, finite exception queues, and one-book-at-a-time certification/promotion.

It does not change textbook truth, curriculum authority, KG semantics, learner state, or production permissions.

## Current milestone boundary

The active milestone remains **Complete Source Maps — 16 logical books**.

Do not start Curriculum Review merely because one or several books are usable. The corpus milestone closes only after every required logical book has an authoritative structural denominator, valid hierarchy and physical binding, source-backed point locators, resolved required exceptions, independent review, certificate, promotion/readback, and the final corpus audit returns `READY_FOR_CURRICULUM_REVIEW`.

A promoted book may be `ready_for_hoc90` before the corpus milestone closes. That state is useful for validation but does not grant permission to replace the approved curriculum process.

## Live refresh rule

At the start of every execution session:

1. read current `main`;
2. read #97 and the retained per-book issue;
3. read live Supabase Source Map readiness;
4. read the latest linked Drive evidence packet;
5. compare exact source IDs, hashes, staging version/digest and unresolved queue.

Newer live backend state overrides dated checkpoints. Never copy a hard count from this document into runtime without a fresh readback.

## Serial closure state machine

One retained issue owns each book.

```text
SOURCE IDENTITY
  ↓
EXTRACTION / INVENTORY
  ↓
FINITE EXCEPTION REVIEW
  ↓
AUTHORITATIVE SCOPE + DENOMINATOR
  ↓
PHYSICAL BINDING + POINT LOCATORS
  ↓
IMMUTABLE STAGING
  ↓
INDEPENDENT REVIEW
  ↓
CERTIFICATE
  ↓
MODE=PROMOTE_ONE
  ↓
ATOMIC PROMOTION + READBACK
  ↓
ready_for_hoc90
```

Candidate counts, bookmark counts and typography inventories are observations, not denominators.

## Roles

Use at most one mutable evidence writer and one genuinely independent reviewer for the same book.

The evidence writer may extract, classify, repair the packet and create a new immutable staging version. That same session is not an independent reviewer of the version it materially authored.

The coordinator owns issue routing, blocker classification and promotion gates. It does not manufacture source evidence.

## Resume contract

Do not rescan a whole book when exact source/scope/parser fingerprints are unchanged.

Every checkpoint must record:

- logical_source_id;
- physical Drive ID(s) and exact SHA-256 when available;
- extraction method/version;
- immutable artifact version/digest;
- completed units;
- remaining exception IDs or exact next operation;
- current blocker class;
- whether any staging/certificate/runtime write occurred.

Resume from the remaining units or finite exception queue.

## No-progress stop conditions

Stop and mark the issue rather than retrying when:

- the same raw Drive object remains inaccessible through the same route;
- the same corrupt source region fails through the same deterministic parser/repair path;
- physical byte identity cannot be proven;
- required hierarchy is ambiguous after available source representations are exhausted;
- an independent reviewer is unavailable;
- source evidence still contains required `REVIEW_REQUIRED`, `SOURCE_GAP`, or unclassified observations.

A retry requires materially new evidence or an authorized new route.

## Blocker vocabulary

Use explicit states:

- `SOURCE_GAP` — source material needed for the required claim/identity is absent.
- `ACCESS_GAP` — source exists but exact bytes cannot currently be read/verified.
- `SOURCE_CORRUPTION_GAP` — registered bytes do not yield the required content.
- `REVIEW_REQUIRED` — evidence exists but human/independent classification is unresolved.
- `INPUT_READY` — bounded deterministic work can proceed without inventing evidence.
- `READY_FOR_CERTIFICATE` — immutable staging has zero required gaps/reviews and independent attestation.
- `ready_for_hoc90` — certificate was promoted and runtime readback matches exact staging.

These states must not be collapsed into a generic percentage.

## Promotion gate

Certification and promotion remain separate.

Certification requires the exact immutable staging digest, full-book scope, authoritative denominator, source fingerprint, hierarchy/locator QA, zero required unresolved cases, and independent reviewer metadata.

Promotion requires separately recorded owner authorization with exact `MODE=PROMOTE_ONE`, logical source ID, staging version/digest and expected runtime version. Promotion must use the guarded atomic path and immediate exact readback.

Never bulk-promote the corpus.

## Current scheduling rule

After the completed Costanzo pilot, choose the next **input-ready** book from live state. Prefer a book with exact source binding and a finite deterministic queue over one blocked by raw access or source corruption.

As of the live refresh on 2026-09-27:

- Costanzo, Kandel and Magee have completed certificate/promotion/readback and are `ready_for_hoc90`;
- the first exact Costanzo HỌC90 pilot is live, and Source Map evidence links are hardened against stale-version/silent-fallback failures;
- Kisner #166 is the current input-ready serial Source Map evidence target with an exact fingerprinted single-file source;
- Katzung #124 has independently approved audit tooling but is parked at a required Appendix 1–3 physical-source gap; denominator remains NULL;
- Robbins is parked at a registered-source corruption gap in its bounded middle-body interval;
- Neumann is reduced to canonical Part 3/full-book access/binding evidence;
- Junqueira remains blocked by registered-source Chapter 23 corruption/recovery evidence;
- Stryer retains its exact-source finite exception queue for a later serial turn;
- all other books remain pending source-map authoring/reconciliation according to fresh live readiness.

This paragraph is a checkpoint, not a permanent queue. Refresh before acting.

## Current serial operation: Kisner

Kisner #166 currently owns the mutable `source-map:kisner-therapeutic-exercise` work key.

The evidence-writer operation is bounded to:

1. exact registered Drive identity/fingerprint readback;
2. internal title/edition/year evidence;
3. printed/native hierarchy inventory;
4. deterministic structural-vs-supplement classification;
5. exact physical point locators with `page_end=null` unless the source directly verifies a range;
6. a finite REVIEW_REQUIRED/SOURCE_GAP ledger and durable evidence packet;
7. independent review before any denominator/staging proposal.

Do not open a second mutable Kisner issue while #166 is active.

## Katzung parked checkpoint

Katzung's exact 20-chunk audit tooling is independently approved for audit use, but that approval does not establish the denominator. The finite main-text queues remain useful evidence work. Closure is currently blocked because the registered 20 chunks do not contain required Appendices 1–3. Do not construct appendix locators from an unregistered comparison attachment or infer them from the printed Contents. Resume certification work only after an exact canonical physical source covering the appendices is registered/fingerprinted.

The historical full-book candidate pool remains diagnostic evidence only.

## Corpus completion gate

After all 16 books individually pass certificate/promotion/readback:

1. refresh live counts and exact readiness for all 16;
2. verify zero blocking required reviews/source gaps;
3. run the final independent corpus audit;
4. require an explicit `READY_FOR_CURRICULUM_REVIEW` result;
5. then begin Curriculum Review with the learner.

Curriculum Review is therefore a milestone transition, not an automatic side effect of Source Map progress.
