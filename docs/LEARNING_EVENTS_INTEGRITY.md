# Learning event integrity

Issue #188 closes a database enforcement gap found during live audit #187.
`append_event()` already inserts immutable identities, but migration 0009 granted
the backend UPDATE/DELETE/TRUNCATE and session deletion cascaded into events.
The forward migration preserves every row, keeps SELECT/INSERT, revokes destructive
table privileges, and guards UPDATE/DELETE/TRUNCATE even for a table owner.
A session with recorded events must be paused/completed/abandoned, not deleted.

## Validation and deployment

The `Learning events integrity` workflow uses isolated PostgreSQL 17, actual core
and runtime migrations, and a transactional contract. It verifies backend insertion,
duplicate-ID rejection, denied mutation, blocked session cascade, owner-level trigger
enforcement, blocked TRUNCATE CASCADE, and fixture rollback. No production secret is
used by this test. Normal migration dry-run and independent review precede merge.
The existing migration workflow applies reviewed pending migrations on main.

Post-deployment: read migration history, both enabled trigger definitions, effective
backend privileges and pre/post event/session counts. Preserve the original event
digest. Run the SQL contract only inside its BEGIN/ROLLBACK on an authorized backend;
never replace rollback with fixture deletion. Do not infer learner mastery from a test.

## Blast radius and remediation

Only destructive operations on `mls_learning_events`, and parent operations that
would destroy those events, change behavior. Existing application append/read and
session updates remain compatible. Brief table locks are needed for trigger creation.
Database owners can still change schema or disable triggers: this is integrity
enforcement for normal operations, not protection against a privileged administrator.

Prefer forward remediation. Incorrect learner facts should be corrected by new events
with explicit references to the earlier event, preserving original evidence. This
migration does not define a new event type or automatically replay aggregate state.

If the deployment must be reversed, an independently reviewed forward migration can
drop `mls_learning_events_append_only` and `mls_learning_events_no_truncate`, drop
`mls_reject_learning_event_mutation()`, and restore the old backend privileges.
That rollback weakens protection and requires an explicit maintenance decision;
it never requires deleting existing data or altering migration history.
