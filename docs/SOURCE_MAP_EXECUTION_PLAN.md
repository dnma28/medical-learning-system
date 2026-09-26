# Source Map execution plan

Owner-requested stabilization, 2026-09-26. Parent milestone: [#97](https://github.com/dnma28/medical-learning-system/issues/97). Plan change: [#131](https://github.com/dnma28/medical-learning-system/issues/131).

This plan sets execution order and handoff requirements. [AGENTS.md](../AGENTS.md), [the staging/promotion contract](SOURCE_MAP_STAGING_PROMOTION.md), [scope policy](source_map_scope_policy.md), and [the work queue](AI_WORK_QUEUE.md) retain their authority. It does not certify a book, authorize production promotion, change the curriculum, or create an unattended runner.

## Goal and current evidence

Finish one complete, auditable book before increasing throughput. Then reuse the proven process for the remaining books. A completed work session is not a completed Source Map milestone.

Observed at **2026-09-26 03:45:29 UTC**, main `ecd4d60099099d8862e4aeb1baefd34037d7369c`:

| Measure | Observed state |
| --- | --- |
| Logical books / registered physical sources | 16 / 56 |
| Registered physical SHA-256 values | 47 |
| Immutable staging rows | 4: Neumann v1, Costanzo v1/v2/v3 |
| Certificates / runtime Source Map nodes | 0 / 0 |
| Costanzo v3 | 895 nodes including Book; candidate N=894; review required |
| Neumann v1 | 26 nodes including Book; denominator NULL; review required |

These are a dated checkpoint, not assertions about future live state. Hash counts and extracted candidate counts are not completion percentages. Architecture fixes #96/#98/#99/#100 and nested-subsection support #102/#103 are already implemented; do not reopen them without a reproducible defect. Scope policy #121 is merged. Source bindings #117/#120/#122 are evidence to reuse, subject to current identity/fingerprint checks.

The operational bottlenecks are unfinished independent review, duplicate ownership, unresolved scope decisions, repeated source-access attempts, and handoffs that describe progress without an exact resume point. Examples: duplicate Kandel binding PR #126 was closed in favor of #122; Kandel #127/#128 disagree about 193 observations; Costanzo #116 still lacks complete independent structural reconciliation.

## Scheduling and roles

- One coordinator owns scheduling in GitHub Issues. No competing mutable task-state file.
- Until the pilot is promoted and read back, the only active book is **Costanzo**. At most one evidence writer and one independent reviewer work on it. This is a limit, not a requirement to keep both busy.
- **Luna / evidence writer:** package existing evidence, run deterministic missing checks, resolve specifically identified exceptions, and write a new external artifact when needed. No invented reviewer identity, certificate, promotion, curriculum or learner-state change.
- **Sol / independent reviewer:** independently verify the exact frozen source packet and report source-backed PASS or specific changes. If this Sol session authored or materially repaired the packet, a different reviewer must perform the independent review. A fresh role label or model switch inside the author session is insufficient.
- Coordinator/engineer work is explicit and scoped. No new parser, agent framework, platform, database schema or generic runner unless an observed blocker requires it.
- Existing workers on other books finish their current safe operation, save artifacts and record a checkpoint before another batch is scheduled. Do not overwrite their artifacts, infer they stopped from an expired claim, or claim to have stopped an external session. Reassign only after the ownership check in AI_WORK_QUEUE.md.
- Before another book starts, finish review/corrections of the current book or record a genuine external blocker. During pilot stabilization, an externally blocked Costanzo remains the pilot; its blocker triggers one consolidated action request, not an unannounced switch to a second pilot.
- After the pilot passes, process remaining books serially. Consider a second independent book only after **two consecutive books** pass the same end-to-end process and an actual review slot exists. Certification/promotion remains serial per book.

Issue body changes and claim acknowledgments do not automatically control already running sessions. New/resumed sessions must read the current #97 operating summary and their issue before writing.

## Execution sequence

| Phase | Work | Exit evidence |
| --- | --- | --- |
| 0. Reconcile ownership | Read main, active claims, latest packet and runtime version once. Preserve in-flight work. Pin source, parser, scope policy and artifact identity. | One writer, an eligible reviewer, exact input manifest and finite exception list. |
| 1. Close Costanzo audit | Review #116 against the exact original, v3 and supplemental evidence. Resolve the structural inventory and classification gaps described below. | Independent PASS on the exact reviewed content, or CHANGES_REQUIRED/BLOCKED with item IDs, locators and reopening conditions. |
| 2. Prepare certifiable version | If the audit passes, prepare the next immutable staging version, expected v4 only if live state still permits. Apply genuine verified statuses and reviewer/QA evidence. | Validator passes; final digest exists; independent reviewer attests the final version and content diff. No implicit v3-to-v4 approval. |
| 3. One-book pilot | With existing explicit MODE=PROMOTE_ONE authorization and all contract gates, certify/promote using current expected runtime version. | Atomic success and exact certificate/version/node/fingerprint/readiness readback. On failure, preserve prior runtime and report the actual error. |
| 4. Remaining books | Select the next input-ready book from the queue. Repeat the same packet → review → final-version → authorized promotion process. | Per-book terminal result; blocked books retain their missing inputs without holding up unrelated books after the pilot. |
| 5. Corpus acceptance | Reconcile all 16 registered logical books with their current certificates and promoted versions. | All 16 full-book contracts pass; zero required unresolved cases; current readiness is true for each. Only then schedule the separate Curriculum Review decision. |

Stage preparation/insertion and service-role operations still follow the issue's declared permissions and current contract. The existing #116 evidence task is not expanded into a promotion task by this document. Do not repeatedly request authorization already recorded for an exact action; do not infer a promotion authorization from a request to revise the plan.

## Costanzo: the first completion target

Use [#116](https://github.com/dnma28/medical-learning-system/issues/116) as the audit task; its source/artifact links and later review observations must be read together.

- Registered source: `costanzo-physiology--b21837a317f0`; original Drive `1ZxRSVJ9VQSY1epivsJE67wvYvEljTZFZ`; 16,313,492 bytes; 493 PDF pages.
- Physical SHA-256: `e71a320ed2c9b4f930dfe45a013255f022a253d4dbf70dee91759937d5ab6e8d`.
- Immutable v3 database digest: `5140f8c0aad6e75e084bcc4c24d19690b17619b5ec96c3a17f089ac7b765e2c6`. The external payload file has a different file hash; never substitute it for this digest.
- Candidate structural N=894, plus Book root; v3 candidate statuses and null independent attestation do not certify as-is.
- Scope #121 already separates 35 unique Clinical Physiology BOX identities and 26 SAMPLE PROBLEM starts into supplemental evidence. Reuse this decision; change it only with an item-specific conflict with source structure.

The remaining independent review is a concrete closure job:

1. Verify the original source identity and exact v3 content; obtain existing per-identity QA, chapter TOC/native-outline reconciliation and supplemental ledgers from #116.
2. Independently reproduce or equivalently audit the reported seven-style scan of **1,090 extracted lines**, including the claimed 1,014 heading/fragment matches, 62 caption starts and 14 wrapped residual lines. These are prior observations, not independent PASS evidence. Explain every remaining line with a stable identity and source locator.
3. Reconcile the subsequent **74 unique table observations** with the earlier style-limited caption scan. Different extraction scopes need a crosswalk, not an assumed numerical contradiction. Confirm no structural classes outside the chosen seven were missed and retain supplemental teaching objects separately.
4. Verify full structural identity coverage, source-supported exclusions/inclusions, deep parent/depth/order topology, printed/PDF page mapping and point locators. Sampling cannot substitute for the full required inventory. Keep `page_end=null` unless a range is directly source-verified.
5. Return one finite verdict. PASS requires zero required unresolved and zero unclassified structural observations. CHANGES_REQUIRED names exact edits and affected identities. BLOCKED names missing evidence and the condition that would make review possible. Do not repeatedly produce a new overall progress report with the same unresolved list.
6. If corrections change hierarchy, locator, identity or scope, the author produces a successor and the reviewer rechecks the affected content plus global invariants. After verified statuses/audit metadata are applied, attest the final immutable digest, not merely the older candidate.

## Freeze inputs, then review the delta

Every review packet identifies: logical/physical source IDs; Drive IDs and available revision evidence; source SHA-256; extraction hash/parser version and settings; scope-policy commit; artifact version and checksum; staging digest if present; included identities; exclusions/supplements; exception IDs; previous accepted checkpoint; and author/reviewer session provenance. No textbook text or PDFs in GitHub.

Scope policy #121 is the starting contract. A recurring label is not automatically supplemental: source hierarchy decides. Do not settle the Kandel 1,256 versus 1,063 disagreement by arithmetic or model preference. Review the 193 exact observations under the policy.

Reuse intact, fingerprint-matching artifacts. Invalidate only what changed:

| Change | Minimum work reopened |
| --- | --- |
| Source bytes/revision or physical binding changes | Affected source extraction, locators and dependent coverage; re-review affected evidence. |
| Parser/settings/extraction changes | Affected output and its reconciliation; retain the old version for comparison. |
| Scope policy changes | Affected classifications and denominator/topology checks; identify the policy diff. |
| Artifact content changes | Changed identities plus global count/topology invariants and the final digest attestation. |
| Unrelated code/docs merge | Check relevance; do not automatically re-extract an unchanged book. |

Review independence still requires independent source-based validation; reusing a manifest does not mean accepting its author's PASS. A registered historical hash proves the earlier bound bytes, not an unobserved current download. Use the registered identity/revision and available source bytes consistently, and record any inability to establish the current binding.

## Checkpoint and retry contract

After every bounded chapter/part batch, save immutable output externally and update the existing issue with a compact checkpoint. This record is coordination metadata, not a new Supabase schema:

```text
run_id / issue / role / author_session / reviewer_session
base_main / scope_policy_commit
source_ids / drive_ids / source_sha256 / available_revision_evidence
parser_version / settings / extraction_sha256
artifact_uri / version / artifact_sha256 / staging_version_and_digest_if_any
completed_units / remaining_units / stable_exception_ids
checks_run / results / changed_since_previous_checkpoint
current_runtime_version_if_relevant
outcome: IN_PROGRESS | CHANGES_REQUIRED | AUDIT_PASS | BLOCKED | PROMOTED
next_action: exact existing command, or exact tool inputs if no CLI exists
blocker / required_new_input / owner / claim_expiry_utc
```

Do not put signed URLs, credentials, textbook passages or learner records in this record. Temporary local paths alone are not a durable handoff. If an exact command does not exist, record the actual tool operation and input IDs; do not invent a CLI.

- Continue authorized dependent work while inputs and session capacity remain. Save progress without ending merely at a chapter boundary or asking for another “continue”. A review dependency is a real boundary; its author cannot self-approve to keep moving.
- At resume, read current main/claim/packet/runtime deltas, verify relevant fingerprints, and start at `remaining_units` or the listed exceptions. Do not bootstrap all 16 books again.
- At most **two attempts total per transient failing read route** with unchanged inputs. A known authorization denial, transfer-size limit or source corruption is blocked immediately; repeating it is not recovery. A materially different authorized route may be attempted with the reason recorded. Never bypass access controls.
- A deterministic parser/validation failure is retried only after an identified input/code/configuration change. Preserve successful earlier batches.
- On an ambiguous production write/timeout, read back operation/version state before any retry. Never blindly repeat a certificate/promotion write. Version conflicts require reconciliation.
- If a correction cycle leaves the same exception set and adds no evidence, stop that cycle as BLOCKED and specify the missing input or scope decision. Do not generate another nominal version. Independent new findings remain blockers even if they invalidate an earlier estimate.
- Before tool/context/budget limits, persist the checkpoint and report its exact continuation. An ended chat session does not run in the background.

## Current queue disposition

The following is scheduling guidance based on the dated snapshot, not ownership reassignment. Re-read actual claims before work. Preserve all conflicting and historical artifacts.

| Work | Disposition | Next admissible action |
| --- | --- | --- |
| Costanzo #116 | First closure target | Finish independent review, then final-version attestation and separately authorized pilot. |
| Kandel #127/#128 | One later book; overlapping #128 is stopped | Retain both drafts; review the 193-observation scope conflict, then complete omitted-body-heading QA. #122 owns the merged binding; #126 was closed as duplicate. Neither 1,256 nor 1,063 is authoritative. |
| Katzung #124 | Queue after pilot; preserve active checkpoint | Reuse registered Part 1 recovery #117; reconcile all 20 chunks and full hierarchy including Chapters 1–67/appendices. The 87 outline observations are not full-book N. |
| Stryer #129 / Robbins #130 | Finish safe current operation; queue next batch | Keep existing deterministic artifacts; verify actual logical/source IDs in registry, binding and finite exception inventory before admitting the next book. An expired claim does not prove a session stopped. |
| Neumann #125 | Source-binding and scope gaps | Reuse existing Part 1/2 hash evidence subject to identity checks. Resolve required Part 3 binding/access; reconcile appendix hierarchy and the 11 text-match exceptions with visual/page evidence. Candidate 685 is not final and must not be blindly incremented by 19. |
| Junqueira #123 | Source corruption gap | Reopen with a verified same-edition alternate or a reproducible recovery against original bytes. Other-edition locators cannot repair missing 17e evidence. |
| Other registered books | Backlog | Select from the live registry after pilot, by source availability and finite review workload. No new all-book extraction campaign. |
| Tooling/context #113/#115 | Separate docs/config work | Preserve their scopes; reconcile any later merge with this plan. They are not prerequisites for completing Costanzo. |

For Neumann, registered whole-file access is also unresolved. Required source coverage must be demonstrated for the chosen physical source set. Do not repeatedly fetch an inaccessible whole-file duplicate when already proven parts serve a specific check; do not silently drop a required binding or claim that the current incomplete part set proves full-book readiness.

## What “one run” means

The target is one coordinated workflow with automatic continuation between authorized steps, durable results and finite terminal outcomes. It does not guarantee that all 16 books will pass despite unavailable/corrupted source bytes or a missing independent reviewer.

- **Run complete:** every admitted task has a saved result or an explicit blocker with its next input; no task disappeared at a context boundary.
- **Audit complete:** one exact packet has genuine independent PASS; this alone is not runtime readiness.
- **Pilot complete:** one authorized book has a valid certificate, atomic promotion and successful live readback.
- **Milestone complete:** all 16 full-book contracts/readbacks pass. A parked blocker keeps the milestone incomplete.

Report only useful deltas: newly completed units, resolved/new exceptions, new certificates/promotions, blocked inputs, and the next action. Do not use candidate totals, repeated scans, issue counts or new tools as proxies for completion.

A single chat cannot invoke an already ended independent session or promise unattended execution. If a truly unattended job is still required after the pilot, make it a bounded engineering task: reuse existing infrastructure where appropriate, define durable job/checkpoint ownership, explicit credentials/access, budget/time limits, retry/readback rules and a real independent review gate; implement and test against the proven pilot before claiming that capability. A compilation/learner queue is not automatically a Source Map runner. No new runner is implemented by this plan.
