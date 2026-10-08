"""One fixed plan, one reviewed-main activation, separately recorded owner gate."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from .identity_backend_preflight import connection_parameters
from .identity_correction import IdentityCorrectionPlan, canonical_json_sha256
from .postgres_identity_correction import (
    _verify_plan,
    apply_identity_correction,
    read_identity_snapshot,
)

REPOSITORY = "dnma28/medical-learning-system"
OWNER_LOGIN = "dnma28"
OWNER_ID = 331470099
ISSUE = 216
BOOK = "costanzo-physiology"
PLAN_SHA256 = "1cfcf79fee5bd981d3922fa5a201252d8273989ebdfa12e304a058a9fc926fd5"
ZIP_SHA256 = "1716e306734340e47d77d156f3a8bac1a5306ef450d1451aec5f840bb6ed0abc"
WORK_KEY = "source-map:costanzo-physiology:identity-apply:1cfcf79f:v1-20261008"
MARKER = "MLS-Owner-Gate\n"
PLAN_PATH = Path("config/identity/costanzo-identity-plan-v3.json")
GUARDS = ("physical_sources", "staging_rows", "certificate_rows")


def _emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def load_plan():
    value = json.loads(PLAN_PATH.read_text())
    if canonical_json_sha256(value) != PLAN_SHA256 or value.get("logical_source_id") != BOOK:
        raise ValueError("fixed plan mismatch")
    return IdentityCorrectionPlan(**value)


def runtime_tree(environment):
    if any(environment.get(k) != v for k, v in {
        "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "push", "GITHUB_RUN_ATTEMPT": "1",
    }.items()):
        raise ValueError("requires first reviewed-main push attempt")
    commit = environment.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid executable commit")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != commit:
        raise ValueError("checkout differs from event commit")
    if not re.fullmatch(r"[0-9]+", environment.get("GITHUB_RUN_ID", "")):
        raise ValueError("invalid run id")
    return subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip()


def validate_gate(gate, tree_sha):
    expected = {
        "status": "APPROVED_FOR_PRODUCTION_APPLY", "logical_source_id": BOOK,
        "plan_sha256": PLAN_SHA256, "zip_sha256": ZIP_SHA256,
        "reviewed_tree_sha": tree_sha, "execution_work_key": WORK_KEY,
    }
    if (any(gate.get(k) != v for k, v in expected.items())
        or gate.get("production_apply_authorized") is not True
        or gate.get("production_rollback_authorized") is not False
        or not isinstance(gate.get("owner_decision_source"), str)
        or not gate["owner_decision_source"].strip()
        or any(type(gate.get(k)) is not int or gate[k] <= 0 for k in (
            "owner_packet_comment_id", "plan_review_comment_id", "code_review_id",
        ))):
        raise ValueError("separate exact owner gate absent or incompatible")


def owner_gate(tree_sha):
    # Fixed public resource only; no credentials, returned URLs or pagination guesses.
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/issues/{ISSUE}/comments?per_page=100",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "mls-identity-gate"},
    )
    with urlopen(request, timeout=15) as response:
        comments = json.load(response)
        if response.headers.get("Link") or len(comments) >= 100:
            raise ValueError("owner record population requires reconciliation")
    for comment in reversed(comments):
        user = comment.get("user", {})
        body = comment.get("body", "")
        if user.get("login") == OWNER_LOGIN and user.get("id") == OWNER_ID and body.startswith(MARKER):
            gate = json.loads(body[len(MARKER):])
            validate_gate(gate, tree_sha)
            return gate | {"actual_owner_gate_comment_id": comment["id"]}
    raise ValueError("no separate owner gate record")


def _execute_once(connection, plan, gate, tree_sha, run_id):
    validate_gate(gate, tree_sha)
    if canonical_json_sha256(plan.model_dump()) != PLAN_SHA256 or plan.logical_source_id != BOOK:
        raise ValueError("fixed execution plan mismatch")
    before = read_identity_snapshot(connection, BOOK)
    _verify_plan(plan, before)
    scope = {"logical_source_id": BOOK, "operation": "identity_apply_once",
             "plan_sha256": PLAN_SHA256, "zip_sha256": ZIP_SHA256, "reviewed_tree_sha": tree_sha}
    manifest = {"scope": scope, "work_key": WORK_KEY,
                "owner_gate_comment_id": gate["actual_owner_gate_comment_id"]}
    with connection.cursor() as cursor:
        cursor.execute("SELECT public.mls_claim_source_map_work(%s,%s,%s,%s,%s,%s,%s)", (
            WORK_KEY, BOOK, "identity-apply-1cfcf79f-v1-20261008", "github-actions-" + run_id,
            canonical_json_sha256(scope), canonical_json_sha256(manifest), 600,
        ))
        lease = cursor.fetchone()[0]
    # No retry/release/rollback on failure, including an ambiguous COMMIT result.
    _emit({"status": "APPLY_ATTEMPT_BEGIN", "plan_sha256": PLAN_SHA256, "work_key": WORK_KEY})
    receipt = apply_identity_correction(connection, plan, authorized_logical_source_id=BOOK,
                                        approved_plan_sha256=PLAN_SHA256, dry_run=False)
    _emit({"status": "ACTUAL_COMMITTED_RECEIPT", "receipt": receipt})
    after = read_identity_snapshot(connection, BOOK)
    business = {k: v for k, v in after["logical_row"].items() if k != "updated_at"}
    if (canonical_json_sha256(after["logical_row"]) != receipt["after_row_sha256"]
        or after["logical_row"]["updated_at"] != receipt["after_updated_at"]
        or business != plan.expected_after_business_row
        or any(after[k] != before[k] for k in GUARDS)):
        raise ValueError("committed receipt requires readback reconciliation")
    proof = {"status": "ACTUAL_COMMIT_READBACK_PASS", "receipt": receipt,
             "snapshot_sha256": canonical_json_sha256(after),
             "guard_counts": {k: len(after[k]) for k in GUARDS},
             "guard_sha256": {k: canonical_json_sha256(after[k]) for k in GUARDS},
             "owner_gate_comment_id": gate["actual_owner_gate_comment_id"]}
    _emit(proof)
    with connection.cursor() as cursor:
        cursor.execute("SELECT public.mls_complete_source_map_work(%s,%s,%s,%s)", (
            WORK_KEY, lease["lease_token"],
            f"https://github.com/{REPOSITORY}/actions/runs/{run_id}", canonical_json_sha256(proof),
        ))
        if cursor.fetchone()[0] is not True:
            raise ValueError("execution completion not acknowledged")
    _emit({"status": "EXECUTION_LEASE_COMPLETED", "work_key": WORK_KEY})
    return receipt


def main():
    phase = "OWNER_GATE"
    try:
        import psycopg

        tree_sha = runtime_tree(os.environ)
        plan = load_plan()
        gate = owner_gate(tree_sha)
        phase = "BACKEND_CONNECTION"
        parameters = connection_parameters(os.environ)
        with psycopg.connect(**parameters) as connection:
            phase = "EXECUTION"
            _execute_once(connection, plan, gate, tree_sha, os.environ["GITHUB_RUN_ID"])
    except Exception as exc:  # noqa: BLE001 -- fail closed without leaking backend details
        # Driver details, URLs, rows and lease tokens must never appear in errors.
        _emit({"status": "STOPPED_NO_RETRY", "phase": phase, "error_class": type(exc).__name__,
               "next_action": "inspect actual receipt and live state; do not rerun or rollback"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
