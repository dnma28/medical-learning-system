"""Synthetic isolated-Postgres tests; never use a production DSN."""

import copy
import os
import threading
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg import sql

from medical_learning_system import postgres_identity_correction as executor
from medical_learning_system.identity_correction import (
    PROVENANCE_NAMESPACE,
    canonical_json_sha256,
    prepare_identity_correction,
)


def approval(plan):
    return {
        "authorized_logical_source_id": plan.logical_source_id,
        "approved_plan_sha256": canonical_json_sha256(plan.model_dump()),
    }


def make_plan(snapshot, patch=None):
    return prepare_identity_correction(
        **snapshot,
        expected_before_sha256=canonical_json_sha256(snapshot["logical_row"]),
        identity_patch=patch if patch is not None else {
            "edition": "6", "publication_year": 2018, "identity_status": "verified",
        },
        metadata_value={"test_only": True, "evidence": {"ids": ["synthetic"]}},
    )


@pytest.fixture
def database():
    dsn = os.environ.get("MLS_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("isolated Postgres DSN not configured")
    connection = psycopg.connect(dsn, autocommit=True)
    # These fixtures INSERT persistent rows into the ephemeral migrated CI DB.
    # No truncate, production endpoint, schema replacement or broad cleanup.
    if connection.info.host not in {"127.0.0.1", "localhost"} or connection.info.port != 54322:
        connection.close()
        pytest.fail("identity fixtures require loopback isolated Supabase port 54322")
    book = "test-identity-" + uuid.uuid4().hex
    other = book + "-other"
    for logical_id in (book, other):
        connection.execute(
            "INSERT INTO public.mls_logical_sources "
            "(logical_source_id,title,kind,edition,identity_status,source_map_state,metadata) "
            "VALUES (%s,'Synthetic identity fixture','textbook','6','verify_from_source',"
            "'unmapped',%s::jsonb)",
            (logical_id, '{"notes":["preserve"],"unicode":"Tiếng Việt","audit":{"version":1}}'),
        )
    for suffix in ("z", "a"):
        connection.execute(
            "INSERT INTO public.mls_sources "
            "(source_id,logical_source_id,provider,provider_file_id,title,mime_type,"
            "modified_time,kind,status,metadata_fingerprint,content_sha256) "
            "VALUES (%s,%s,'synthetic',%s,'Synthetic PDF','application/pdf',"
            "now(),'textbook','new',%s,%s)",
            (book + suffix, book, book + suffix, "b" * 64, "c" * 64),
        )
    for version in (1, 2):
        connection.execute(
            "INSERT INTO public.mls_source_map_staging "
            "(logical_source_id,staging_version,proposal,toc_denominator,audit_metadata,payload_sha256) "
            "VALUES (%s,%s,'[]',1,'{}','trigger-computes-digest')", (book, version),
        )
    add_certificate(connection, book, 1)
    try:
        yield connection, book, other
    finally:
        connection.close()


def add_certificate(connection, book, version):
    connection.execute(
        "INSERT INTO public.mls_source_map_certificates "
        "(logical_source_id,staging_version,staging_sha256,certificate_sha256,"
        "toc_denominator,audit_metadata) SELECT logical_source_id,staging_version,payload_sha256,"
        "%s,1,'{}' FROM public.mls_source_map_staging WHERE logical_source_id=%s "
        "AND staging_version=%s",
        (canonical_json_sha256([book, version]), book, version),
    )


def test_approval_checks_run_before_accessing_connection():
    snapshot = {
        "logical_row": {"logical_source_id": "synthetic", "updated_at": "exact", "metadata": {}},
        "physical_sources": [], "staging_rows": [], "certificate_rows": [],
    }
    plan = make_plan(snapshot)
    with pytest.raises(ValueError, match="owner scope"):
        executor.apply_identity_correction(None, plan, **(approval(plan) | {
            "authorized_logical_source_id": "other",
        }))
    with pytest.raises(ValueError, match="approved plan digest"):
        executor.apply_identity_correction(None, plan, **(approval(plan) | {
            "approved_plan_sha256": "0" * 64,
        }))


@pytest.mark.parametrize("dry_run", [None, 0, "false", ""])
def test_invalid_dry_run_cannot_fall_through_to_commit(dry_run):
    for operation, arguments in (
        (executor.apply_identity_correction, (None, None)),
        (executor.rollback_identity_correction, (None, None, {})),
    ):
        with pytest.raises(ValueError, match="dry_run must be a boolean"):
            operation(*arguments, dry_run=dry_run, authorized_logical_source_id="synthetic",
                      approved_plan_sha256="0" * 64)


@pytest.mark.parametrize("autocommit,status", [(False, 0), (True, 2)])
def test_rejects_caller_transaction_before_queries(autocommit, status):
    connection = SimpleNamespace(autocommit=autocommit, info=SimpleNamespace(transaction_status=status))
    with pytest.raises(ValueError, match="idle autocommit"):
        executor.read_identity_snapshot(connection, "synthetic")


@pytest.mark.parametrize("patch", [None, {}])
def test_apply_and_guarded_rollback_preserve_every_other_field(database, patch):
    connection, book, other = database
    before = executor.read_identity_snapshot(connection, book)
    other_before = executor.read_identity_snapshot(connection, other)
    plan = make_plan(before, patch)
    receipt = executor.apply_identity_correction(connection, plan, **approval(plan))
    after = executor.read_identity_snapshot(connection, book)
    assert receipt["committed"] is True
    assert canonical_json_sha256(after["logical_row"]) == receipt["after_row_sha256"]
    assert after["logical_row"]["updated_at"] != before["logical_row"]["updated_at"]
    assert executor._business(after["logical_row"]) == plan.expected_after_business_row
    for label, _, _ in executor._GUARDS:
        assert after[label] == before[label]
    assert executor.read_identity_snapshot(connection, other) == other_before
    preview = executor.rollback_identity_correction(
        connection, plan, receipt, dry_run=True, **approval(plan),
    )
    assert preview["committed"] is False
    assert executor.read_identity_snapshot(connection, book) == after
    executor.rollback_identity_correction(connection, plan, receipt, **approval(plan))
    restored = executor.read_identity_snapshot(connection, book)
    assert executor._business(restored["logical_row"]) == executor._business(before["logical_row"])
    assert restored["logical_row"]["updated_at"] != receipt["after_updated_at"]
    assert executor.read_identity_snapshot(connection, other) == other_before
    with pytest.raises(ValueError, match="after-row drifted"):
        executor.rollback_identity_correction(connection, plan, receipt, **approval(plan))


def test_dry_run_leaves_no_mutation_and_receipt_cannot_rollback(database):
    connection, book, _ = database
    before = executor.read_identity_snapshot(connection, book)
    plan = make_plan(before)
    receipt = executor.apply_identity_correction(connection, plan, dry_run=True, **approval(plan))
    assert receipt["committed"] is False
    assert executor.read_identity_snapshot(connection, book) == before
    with pytest.raises(ValueError, match="committed approved plan"):
        executor.rollback_identity_correction(connection, plan, receipt, **approval(plan))


def test_apply_stops_on_any_preimage_change_and_cannot_replay(database):
    connection, book, _ = database
    plan = make_plan(executor.read_identity_snapshot(connection, book))
    receipt = executor.apply_identity_correction(connection, plan, **approval(plan))
    stable = executor.read_identity_snapshot(connection, book)
    with pytest.raises(ValueError, match="preimage drifted"):
        executor.apply_identity_correction(connection, plan, **approval(plan))
    assert executor.read_identity_snapshot(connection, book) == stable
    connection.execute(
        "UPDATE public.mls_logical_sources SET updated_at=clock_timestamp() WHERE logical_source_id=%s",
        (book,),
    )
    drift = executor.read_identity_snapshot(connection, book)
    with pytest.raises(ValueError, match="after-row drifted"):
        executor.rollback_identity_correction(connection, plan, receipt, **approval(plan))
    assert executor.read_identity_snapshot(connection, book) == drift


@pytest.mark.parametrize("changed", ["source", "rebind", "staging", "certificate"])
def test_complete_guard_sets_reject_changes_and_new_rows(database, changed):
    connection, book, other = database
    plan = make_plan(executor.read_identity_snapshot(connection, book))
    if changed == "source":
        connection.execute(
            "UPDATE public.mls_sources SET metadata_fingerprint='changed' WHERE logical_source_id=%s",
            (book,),
        )
    elif changed == "rebind":
        connection.execute(
            "UPDATE public.mls_sources SET logical_source_id=%s WHERE source_id=%s",
            (other, book + "a"),
        )
    elif changed == "staging":
        connection.execute(
            "INSERT INTO public.mls_source_map_staging "
            "(logical_source_id,staging_version,proposal,toc_denominator,payload_sha256) "
            "VALUES (%s,3,'[]',1,'trigger-computes-digest')", (book,),
        )
    else:
        add_certificate(connection, book, 2)
    stable = executor.read_identity_snapshot(connection, book)
    with pytest.raises(ValueError, match="guards drifted"):
        executor.apply_identity_correction(connection, plan, **approval(plan))
    assert executor.read_identity_snapshot(connection, book) == stable


def test_rollbacks_stop_when_guard_rows_change(database):
    connection, book, _ = database
    plan = make_plan(executor.read_identity_snapshot(connection, book))
    receipt = executor.apply_identity_correction(connection, plan, **approval(plan))
    add_certificate(connection, book, 2)
    stable = executor.read_identity_snapshot(connection, book)
    with pytest.raises(ValueError, match="guards drifted"):
        executor.rollback_identity_correction(connection, plan, receipt, **approval(plan))
    assert executor.read_identity_snapshot(connection, book) == stable


def test_tampered_rollback_or_after_plan_is_revalidated_before_write(database):
    connection, book, _ = database
    before = executor.read_identity_snapshot(connection, book)
    plan = make_plan(before)
    bad_rollback = copy.deepcopy(plan.rollback)
    bad_rollback["restore_identity_fields"]["title"] = "must not restore this"
    bad = replace(plan, rollback=bad_rollback)
    with pytest.raises(ValueError, match="plan or"):
        executor.apply_identity_correction(connection, bad, **approval(bad))
    bad_after = copy.deepcopy(plan.expected_after_business_row)
    bad_after["title"] = "must not write this"
    bad = replace(plan, expected_after_business_row=bad_after)
    with pytest.raises(ValueError, match="plan or"):
        executor.apply_identity_correction(connection, bad, **approval(bad))
    assert executor.read_identity_snapshot(connection, book) == before


def test_post_write_readback_failure_rolls_back_all_side_effects(database):
    connection, book, _ = database
    before = executor.read_identity_snapshot(connection, book)
    plan = make_plan(before)
    # An unexpected same-transaction trigger modifies a protected source row.
    connection.execute(
        "CREATE FUNCTION pg_temp.identity_guard_side_effect() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN UPDATE public.mls_sources SET metadata_fingerprint='bad' "
        "WHERE logical_source_id=NEW.logical_source_id; RETURN NEW; END $$"
    )
    trigger = "test_identity_" + uuid.uuid4().hex
    connection.execute(sql.SQL(
        "CREATE TRIGGER {} AFTER UPDATE ON public.mls_logical_sources "
        "FOR EACH ROW WHEN (NEW.logical_source_id={}) "
        "EXECUTE FUNCTION pg_temp.identity_guard_side_effect()"
    ).format(sql.Identifier(trigger), sql.Literal(book)))
    try:
        with pytest.raises(ValueError, match="protected guard rows"):
            executor.apply_identity_correction(connection, plan, **approval(plan))
        assert executor.read_identity_snapshot(connection, book) == before
    finally:
        connection.execute(sql.SQL("DROP TRIGGER {} ON public.mls_logical_sources").format(
            sql.Identifier(trigger),
        ))


def test_concurrent_source_insert_cannot_slip_between_guard_and_update(database, monkeypatch):
    connection, book, _ = database
    plan = make_plan(executor.read_identity_snapshot(connection, book))
    locked, release = threading.Event(), threading.Event()
    original = executor._write_identity
    outcome = []

    def paused_write(*args, **kwargs):
        locked.set()
        assert release.wait(5), "concurrency probe did not finish"
        return original(*args, **kwargs)

    def apply():
        try:
            outcome.append(executor.apply_identity_correction(connection, plan, **approval(plan)))
        except Exception as exc:  # noqa: BLE001 - propagate every worker failure to the test thread
            outcome.append(exc)

    monkeypatch.setattr(executor, "_write_identity", paused_write)
    thread = threading.Thread(target=apply)
    thread.start()
    try:
        assert locked.wait(5), "transaction did not acquire guards"
        with psycopg.connect(os.environ["MLS_TEST_POSTGRES_DSN"], autocommit=True) as contender:
            contender.execute("SET lock_timeout='200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                contender.execute(
                    "INSERT INTO public.mls_sources "
                    "(source_id,logical_source_id,provider,provider_file_id,title,mime_type,"
                    "modified_time,kind,status,metadata_fingerprint) "
                    "VALUES (%s,%s,'synthetic',%s,'Concurrent source','application/pdf',"
                    "now(),'textbook','new','never-committed')",
                    (book + "new", book, book + "new"),
                )
    finally:
        release.set()
        thread.join(6)
    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], dict), outcome
    assert len(executor.read_identity_snapshot(connection, book)["physical_sources"]) == 2


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_public_roles_cannot_read_or_apply(database, role):
    connection, book, _ = database
    plan = make_plan(executor.read_identity_snapshot(connection, book))
    before = executor.read_identity_snapshot(connection, book)
    connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            executor.apply_identity_correction(connection, plan, **approval(plan))
    finally:
        connection.execute("RESET ROLE")
    assert executor.read_identity_snapshot(connection, book) == before


def test_backend_service_role_preserves_existing_grants(database):
    connection, book, _ = database
    plan = make_plan(executor.read_identity_snapshot(connection, book))
    connection.execute("SET ROLE service_role")
    try:
        receipt = executor.apply_identity_correction(connection, plan, **approval(plan))
        assert receipt["committed"] is True
    finally:
        connection.execute("RESET ROLE")
    assert PROVENANCE_NAMESPACE in executor.read_identity_snapshot(connection, book)["logical_row"]["metadata"]
