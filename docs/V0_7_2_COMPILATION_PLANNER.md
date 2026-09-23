# v0.7.2 — Compilation Planner and Queue

The target library is roughly 1000 documents. Full parsing, multimodal
enrichment and embedding are not applied to every document immediately.

## Tiers

```text
CORE
  repeated high-value books
  highest compilation priority

CURRICULUM
  sources needed by the active study plan
  compile when relevant

ARCHIVE
  metadata/catalog only by default
  compile on explicit demand
```

## Planning

The planner currently considers only sources in NEW, STALE or ERROR states.
COMPILED sources are not scheduled by default.

Priority combines tier and source state. CORE always outranks CURRICULUM, while
STALE outranks NEW/ERROR within the same tier.

ERROR sources are excluded once their retry count reaches max_attempts.

## Queue

The queue:
- enforces a bounded planning batch;
- permits one PENDING/RUNNING job per source;
- claims the highest-priority pending job;
- records attempts;
- permits explicit retries until max_attempts.

The queue does not parse PDFs or invoke an LLM/model. It only decides which
source should be compiled next.

## Cloud parity

Migration 0005 mirrors the queue table in Supabase with backend-only RLS. A
future cloud worker will claim jobs using a transaction/RPC so multiple workers
cannot claim the same job concurrently.
