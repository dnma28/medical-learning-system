# One-book identity correction transaction

Refs #196; builds on merged PR #206. This is a backend implementation contract,
not a book identity verdict or permission to apply a correction.

## Boundary

`postgres_identity_correction.py` accepts a caller-supplied psycopg 3 connection.
It creates no connection, public RPC, migration, CLI or catalog-sync route. The
optional `postgres` extra pins the driver. Use a dedicated idle connection with
`autocommit=True`; caller transactions are rejected before any query.
Existing database privileges/RLS apply. No new grant or SECURITY DEFINER bypass
is introduced. Never pass a production credential into a client or Git artifact.

### Backend connection preflight

`identity-backend-preflight.yml` reuses the existing `MLS_SUPABASE_URL` and
`SUPABASE_DB_PASSWORD` GitHub Actions secrets and existing Session pooler target.
Only the backend step receives credentials. It validates the expected project,
uses TLS, a bounded connection/statement timeout and an idle autocommit psycopg
connection, then sets session read-only and calls `read_identity_snapshot` for
Costanzo. Logs contain only canonical hashes/counts, never full source rows,
staging proposals, passwords or a credential-bearing DSN. Connection failures
print the exception class only.

The workflow runs on reviewed configuration changes merged to main or manual
dispatch. It does not run on pull requests and never calls apply/rollback, writes
identity, claims a work lease or creates a public RPC. Its success proves the
backend can connect and read the complete snapshot at that run; it does not
provide a credential to a ChatGPT session or authorize an identity correction.
An actual apply caller still needs its exact reviewed execution route, plan and
owner gate. Do not repurpose the preflight into raw SQL writes or export secrets
to bypass that boundary.

One invocation has exactly one logical book and an exact approved plan digest.
Approval parameters are process bindings, not an authentication mechanism or
source-truth proof. Backend privilege alone does not satisfy the review/owner gate.

## Snapshot and review

1. Read the exact source/policy evidence and resolve the intended fields. A
   copyright date alone must not establish a publication year.
2. `read_identity_snapshot(connection, logical_source_id)` reads complete rows
   in a consistent read-only transaction. It returns the logical row and all
   physical/staging/certificate rows. Physical rows order by `source_id`;
   staging/certificates order by `staging_version`. UTC JSON timestamps retain
   the exact server representation used in plan hashing.
3. Create a **new** `IdentityCorrectionPlan` with the merged preparation helper.
   Bind a new immutable one-book scope/work key, source/policy SHA and complete
   snapshot/plan digests. Do not reuse the historical six-book list-order guards
   or rerun completed v1 work. Preserve source/evidence integrity and any required
   fresh lease under the retained workflow.
4. A fresh independent reviewer checks the exact code HEAD and concrete plan,
   source identity evidence, dry-run/readback and rollback. Owner separately
   authorizes the exact book/plan and production invocation. This code PR has no
   live plan or production approval.

## Apply

`apply_identity_correction` requires `authorized_logical_source_id` and
`approved_plan_sha256` equal to `canonical_json_sha256(plan.model_dump())`.
It copies the input, so external mutations cannot change an in-flight plan.

Within a READ COMMITTED transaction it locks the logical row FOR UPDATE,
then holds brief SHARE table locks over physical sources, staging and
certificates. These block phantom insert/rebinding races even for other writers
that ignore an advisory key. **Other books' writes to those three tables are
also paused until commit**; this intentionally conservative operation is for a
bounded maintenance correction, not a bulk or interactive path. Lock timeout
is 5 seconds and statement timeout 30 seconds. No external I/O occurs under locks.

The executor reproduces every transaction/rollback plan field from the full live
preimage and deterministic guard sets. It updates only the three allowlisted
identity fields, exact preserved metadata plus the absent policy namespace,
and server-generated `updated_at`. It checks the exact business after-state and
unchanged guard rows before commit. Any error rolls the whole transaction back.

Returned receipt binds the full after-row SHA (including the actual server
timestamp), book and plan digest. Return occurs only after transaction exit.
`dry_run=True` executes identical checks but forces rollback and returns
`committed=False`; that receipt cannot authorize rollback of a committed apply.
Both operations reject non-boolean `dry_run` values before accessing a connection.

## Rollback

A separate recorded owner decision must cover rollback. Supply the original
reviewed plan and committed receipt. The transaction locks the same resources,
requires the **entire** current after-row SHA, business SHA, server timestamp,
book and plan digest to match, and rechecks all protected guard sets.
It restores only fields actually present in the identity patch and the exact
metadata preimage. It generates a new server timestamp; it never restores a
whole row, old timestamp, physical row, catalog or Source Map artifact.

Drift, timeout, serialization/deadlock failure or connection error stops the
operation; there is no automatic retry. A lost COMMIT acknowledgment is an
ambiguous outcome: inspect current row and guard state and record a new bounded
decision before any further action. Do not replay the old plan blindly.

## Verification

The existing postgres-contract CI job first applies the full migration chain to
isolated Supabase, then runs `tests/test_postgres_identity_correction.py` against
loopback port 54322. Fixtures contain synthetic identities and leave rows only
in that ephemeral database. They test apply/rollback, provenance-only patches,
dry-run, replay/drift, phantom guards, trigger side-effect rollback, competing
source insert and existing backend/public role permissions. The test fixture
rejects external hosts or ports. Without the optional driver/isolated DSN,
integration checks are explicitly skipped, not claimed as a local PASS.

PostgreSQL lock semantics: https://www.postgresql.org/docs/17/sql-lock.html
Psycopg transaction semantics: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
