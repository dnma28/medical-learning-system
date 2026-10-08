"""Backend-only, one-book transactions; caller records separate owner approval.

Requires an idle psycopg 3 autocommit connection. No DSN, CLI, RPC, catalog sync,
or production connection is supplied here. Database privileges remain enforced.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from .identity_correction import (
    IDENTITY_FIELDS,
    IdentityCorrectionPlan,
    canonical_json_sha256,
    prepare_identity_correction,
)

_GUARDS = (
    ("physical_sources", "mls_sources", "source_id"),
    ("staging_rows", "mls_source_map_staging", "staging_version"),
    ("certificate_rows", "mls_source_map_certificates", "staging_version"),
)


def _idle_connection(connection: Any) -> None:
    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("requires an idle autocommit connection; no caller transaction")


def _settings(cursor: Any, *, read_only: bool = False) -> None:
    isolation = "REPEATABLE READ READ ONLY" if read_only else "READ COMMITTED"
    cursor.execute("SET TRANSACTION ISOLATION LEVEL " + isolation)
    cursor.execute("SET LOCAL TIME ZONE 'UTC'")
    cursor.execute("SET LOCAL lock_timeout = '5s'")
    cursor.execute("SET LOCAL statement_timeout = '30s'")


def _snapshot(cursor: Any, logical_source_id: str, *, lock: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE OF b" if lock else ""
    cursor.execute(
        "SELECT to_jsonb(b) FROM public.mls_logical_sources b "
        "WHERE logical_source_id = %s" + suffix,
        (logical_source_id,),
    )
    result = cursor.fetchone()
    if result is None:
        raise ValueError("logical source not found")
    if lock:
        # Row locks do not cover phantom inserts or rebinding of physical rows.
        # Brief SHARE locks block even writers that do not use our advisory key.
        cursor.execute(
            "LOCK TABLE public.mls_sources, public.mls_source_map_staging, "
            "public.mls_source_map_certificates IN SHARE MODE"
        )
    snapshot = {"logical_row": result[0]}
    for label, table, order in _GUARDS:
        # Identifiers are fixed module constants, never caller input.
        cursor.execute(
            f"SELECT to_jsonb(g) FROM public.{table} g "
            f"WHERE logical_source_id = %s ORDER BY {order}",
            (logical_source_id,),
        )
        snapshot[label] = [row[0] for row in cursor.fetchall()]
    return snapshot


def read_identity_snapshot(connection: Any, logical_source_id: str) -> dict[str, Any]:
    """Read complete consistent rows, in the executor's deterministic guard order.

    Build a NEW plan from this snapshot; historical list-order digests are not
    silently sorted or reused. This read creates no plan or approval by itself.
    """
    _idle_connection(connection)
    with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
        _settings(cursor, read_only=True)
        snapshot = _snapshot(cursor, logical_source_id)
    return snapshot


def _authorized_plan(
    plan: IdentityCorrectionPlan,
    authorized_logical_source_id: str,
    approved_plan_sha256: str,
) -> IdentityCorrectionPlan:
    plan = copy.deepcopy(plan)
    if plan.logical_source_id != authorized_logical_source_id:
        raise ValueError("owner scope does not match the logical book")
    if canonical_json_sha256(plan.model_dump()) != approved_plan_sha256:
        raise ValueError("approved plan digest does not match")
    return plan


def _verify_plan(plan: IdentityCorrectionPlan, snapshot: dict[str, Any]) -> None:
    recreated = prepare_identity_correction(
        **snapshot,
        expected_before_sha256=plan.before_row_sha256,
        identity_patch=plan.identity_patch,
        metadata_value=plan.metadata_value,
        metadata_namespace=plan.metadata_namespace,
    )
    # The catalog description is not executed; all transaction fields must be
    # reproduced from the exact live preimage, including rollback instructions.
    recreated = replace(recreated, catalog_patch=plan.catalog_patch)
    if recreated.model_dump() != plan.model_dump():
        raise ValueError("plan or physical/staging/certificate guards drifted")


def _write_identity(
    cursor: Any,
    logical_source_id: str,
    patch: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    cursor.execute(
        "UPDATE public.mls_logical_sources b SET "
        "edition = CASE WHEN %s THEN %s ELSE edition END, "
        "publication_year = CASE WHEN %s THEN %s ELSE publication_year END, "
        "identity_status = CASE WHEN %s THEN %s ELSE identity_status END, "
        "metadata = %s::jsonb, updated_at = clock_timestamp() "
        "WHERE logical_source_id = %s RETURNING to_jsonb(b)",
        (
            "edition" in patch, patch.get("edition"),
            "publication_year" in patch, patch.get("publication_year"),
            "identity_status" in patch, patch.get("identity_status"),
            json.dumps(metadata, ensure_ascii=False, allow_nan=False), logical_source_id,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("logical source disappeared")
    return row[0]


def _business(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "updated_at"}


def _unchanged_guards(before: dict[str, Any], after: dict[str, Any]) -> None:
    if any(before[label] != after[label] for label, _, _ in _GUARDS):
        raise ValueError("protected guard rows changed during transaction")


def apply_identity_correction(
    connection: Any,
    plan: IdentityCorrectionPlan,
    *,
    authorized_logical_source_id: str,
    approved_plan_sha256: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply one digest-bound plan atomically; no automatic retry on any failure.

    Approval parameters bind a recorded process decision; they are not an
    authentication token or proof of source truth. Caller must supply both gates.
    Dry runs execute the same checks but explicitly roll back before returning.
    """
    if type(dry_run) is not bool:
        raise ValueError("dry_run must be a boolean")
    plan = _authorized_plan(plan, authorized_logical_source_id, approved_plan_sha256)
    _idle_connection(connection)
    with (
        connection.transaction(force_rollback=dry_run),
        connection.cursor(row_factory=tuple_row) as cursor,
    ):
        _settings(cursor)
        before = _snapshot(cursor, plan.logical_source_id, lock=True)
        _verify_plan(plan, before)
        after_row = _write_identity(
            cursor, plan.logical_source_id, plan.identity_patch,
            plan.expected_after_business_row["metadata"],
        )
        after = _snapshot(cursor, plan.logical_source_id)
        _unchanged_guards(before, after)
        if after_row != after["logical_row"] or (
            canonical_json_sha256(_business(after_row)) != plan.expected_after_business_sha256
        ):
            raise ValueError("logical after-state does not match the approved plan")
        receipt = {
            "logical_source_id": plan.logical_source_id,
            "plan_sha256": approved_plan_sha256,
            "after_row_sha256": canonical_json_sha256(after_row),
            "after_updated_at": after_row["updated_at"],
            "committed": not dry_run,
        }
    return receipt


def rollback_identity_correction(
    connection: Any,
    plan: IdentityCorrectionPlan,
    receipt: dict[str, Any],
    *,
    authorized_logical_source_id: str,
    approved_plan_sha256: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Restore only written identity fields and metadata on an exact after-row.

    Never restore updated_at, source fields, or an entire logical row. A separate
    recorded owner decision must cover this rollback invocation as well.
    """
    if type(dry_run) is not bool:
        raise ValueError("dry_run must be a boolean")
    plan = _authorized_plan(plan, authorized_logical_source_id, approved_plan_sha256)
    receipt = copy.deepcopy(receipt)
    if (
        receipt.get("committed") is not True
        or receipt.get("logical_source_id") != plan.logical_source_id
        or receipt.get("plan_sha256") != approved_plan_sha256
    ):
        raise ValueError("rollback receipt does not bind a committed approved plan")
    _idle_connection(connection)
    with (
        connection.transaction(force_rollback=dry_run),
        connection.cursor(row_factory=tuple_row) as cursor,
    ):
        _settings(cursor)
        live = _snapshot(cursor, plan.logical_source_id, lock=True)
        row = live["logical_row"]
        if (
            canonical_json_sha256(row) != receipt.get("after_row_sha256")
            or row["updated_at"] != receipt.get("after_updated_at")
            or canonical_json_sha256(_business(row)) != plan.expected_after_business_sha256
        ):
            raise ValueError("rollback after-row drifted; stop on concurrent change")
        before_row = copy.deepcopy(plan.expected_after_business_row)
        before_row.update(plan.rollback["restore_identity_fields"])
        before_row["metadata"] = copy.deepcopy(plan.rollback["restore_metadata_preimage"])
        before_row["updated_at"] = plan.before_updated_at
        _verify_plan(plan, {**live, "logical_row": before_row})
        restore = plan.rollback["restore_identity_fields"]
        if set(restore) - IDENTITY_FIELDS:
            raise ValueError("rollback contains non-identity fields")
        restored = _write_identity(cursor, plan.logical_source_id, restore, before_row["metadata"])
        after = _snapshot(cursor, plan.logical_source_id)
        _unchanged_guards(live, after)
        if restored != after["logical_row"] or _business(restored) != _business(before_row):
            raise ValueError("rollback did not restore the exact business preimage")
        result = {
            "logical_source_id": plan.logical_source_id,
            "restored_row_sha256": canonical_json_sha256(restored),
            "restored_updated_at": restored["updated_at"],
            "committed": not dry_run,
        }
    return result
