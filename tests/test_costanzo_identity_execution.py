"""Owner gate and one-shot coordination; native fixtures are loopback-only."""

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

psycopg = pytest.importorskip("psycopg")
from test_postgres_identity_correction import database, make_plan  # noqa: F401

from medical_learning_system import costanzo_identity_execution as route
from medical_learning_system.identity_correction import canonical_json_sha256
from medical_learning_system.postgres_identity_correction import read_identity_snapshot

TREE = "a" * 40


def gate():
    return {"status": "APPROVED_FOR_PRODUCTION_APPLY", "logical_source_id": route.BOOK,
            "plan_sha256": route.PLAN_SHA256, "zip_sha256": route.ZIP_SHA256,
            "reviewed_tree_sha": TREE, "execution_work_key": route.WORK_KEY,
            "production_apply_authorized": True, "production_rollback_authorized": False,
            "owner_decision_source": "SYNTHETIC TEST ONLY", "owner_packet_comment_id": 1,
            "plan_review_comment_id": 2, "code_review_id": 3,
            "actual_owner_gate_comment_id": 4}


@pytest.mark.parametrize("change", [
    {"status": "PENDING"}, {"status": "REVOKED"}, {"logical_source_id": "other"},
    {"plan_sha256": "0" * 64}, {"reviewed_tree_sha": "b" * 40},
    {"zip_sha256": "0" * 64}, {"execution_work_key": "old"},
    {"production_apply_authorized": "true"}, {"production_apply_authorized": 1},
    {"production_rollback_authorized": True}, {"owner_decision_source": ""},
    {"code_review_id": True}, {"plan_review_comment_id": 0},
])
def test_gate_requires_separate_exact_binding(change):
    with pytest.raises(ValueError):
        route.validate_gate(gate() | change, TREE)


def test_fixed_plan_matches_verified_external_plan():
    plan = route.load_plan()
    assert canonical_json_sha256(plan.model_dump()) == route.PLAN_SHA256
    assert plan.staging_rows_sha256 == "383a028a0b5adbebc2439749faa98376aa465716dc564e3ec50d5d7050faea6b"
    assert plan.identity_patch == {"edition": "6", "publication_year": 2018, "identity_status": "verified"}


def test_gate_uses_owner_account_and_latest_record_without_falling_back():
    valid = {"id": 10, "user": {"id": route.OWNER_ID, "login": route.OWNER_LOGIN},
             "body": route.MARKER + json.dumps(gate())}
    response = MagicMock()
    response.__enter__.return_value = response
    response.headers = {}
    with patch.object(route, "urlopen", return_value=response) as fetch, patch.object(
        route.json, "load", return_value=[valid,
                                         valid | {"user": {"login": "other", "id": 0}},
                                         valid | {"id": 11, "body": route.MARKER + json.dumps(gate() | {"status": "REVOKED"})}],
    ), pytest.raises(ValueError):
        route.owner_gate(TREE)
    assert fetch.call_args.kwargs["timeout"] == 15
    assert fetch.call_args.args[0].full_url == (
        "https://api.github.com/repos/dnma28/medical-learning-system/issues/216/comments?per_page=100"
    )
    with patch.object(route, "urlopen", return_value=response), patch.object(route.json, "load", return_value=[valid]):
        assert route.owner_gate(TREE)["actual_owner_gate_comment_id"] == 10
    response.headers = {"Link": "more"}
    with patch.object(route, "urlopen", return_value=response), patch.object(route.json, "load", return_value=[valid]), pytest.raises(ValueError, match="population"):
        route.owner_gate(TREE)


@pytest.mark.parametrize("change", [
    {"GITHUB_REF": "refs/heads/unreviewed"}, {"GITHUB_RUN_ATTEMPT": "2"},
    {"GITHUB_REPOSITORY": "other/repo"}, {"GITHUB_EVENT_NAME": "workflow_dispatch"},
    {"GITHUB_SHA": "HEAD;danger"}, {"GITHUB_RUN_ID": "x"},
])
def test_runtime_rejects_branch_dispatch_rerun_and_wrong_checkout(change):
    env = {"GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ATTEMPT": "1",
           "GITHUB_REPOSITORY": route.REPOSITORY, "GITHUB_EVENT_NAME": "push",
           "GITHUB_SHA": "c" * 40, "GITHUB_RUN_ID": "1"} | change
    with patch.object(route.subprocess, "check_output", return_value="c" * 40), pytest.raises(ValueError):
        route.runtime_tree(env)


def test_missing_gate_stops_before_connection_and_redacts_errors(capsys):
    with patch.object(route, "runtime_tree", return_value=TREE), patch.object(
        route, "owner_gate", side_effect=ValueError("secret-url-or-password"),
    ), patch("psycopg.connect") as connect:
        assert route.main() == 1
        connect.assert_not_called()
    output = capsys.readouterr().out
    assert "secret-url-or-password" not in output
    assert "STOPPED_NO_RETRY" in output and '"phase": "OWNER_GATE"' in output


def test_backend_connection_failure_redacts_password_and_never_executes(capsys):
    with patch.object(route, "runtime_tree", return_value=TREE), patch.object(
        route, "owner_gate", return_value=gate(),
    ), patch.object(route, "connection_parameters", return_value={}), patch(
        "psycopg.connect", side_effect=psycopg.OperationalError("private-password"),
    ), patch.object(route, "_execute_once") as execute:
        assert route.main() == 1
        execute.assert_not_called()
    assert "private-password" not in capsys.readouterr().out


def test_fixed_plan_drift_and_decimal_representation_reject_before_lease():
    snapshot = {"logical_row": {"logical_source_id": route.BOOK, "updated_at": "before", "metadata": {}},
                "physical_sources": [], "staging_rows": [{"logical_source_id": route.BOOK, "bbox": [12]}],
                "certificate_rows": []}
    plan = make_plan(snapshot)
    changed = copy.deepcopy(snapshot)
    changed["staging_rows"][0]["bbox"] = [12.0]
    connection = MagicMock()
    with patch.object(route, "read_identity_snapshot", return_value=changed), patch.object(
        route, "PLAN_SHA256", canonical_json_sha256(plan.model_dump()),
    ), pytest.raises(ValueError, match="guards drifted"):
        route._execute_once(connection, plan, gate(), TREE, "1")
    connection.cursor.assert_not_called()


def test_execution_failure_never_retries_or_completes_lease():
    plan = route.load_plan()
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.side_effect = [[False], [{"lease_token": "private-token"}]]
    with patch.object(route, "read_identity_snapshot"), patch.object(route, "_verify_plan"), patch.object(
        route, "apply_identity_correction", side_effect=psycopg.OperationalError("COMMIT uncertain"),
    ) as apply, pytest.raises(psycopg.OperationalError):
        route._execute_once(connection, plan, gate(), TREE, "1")
    assert apply.call_count == 1
    calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    assert sum("mls_claim_source_map_work" in call.args[0] for call in calls) == 1
    assert all("mls_complete_source_map_work" not in call.args[0] for call in calls)


def test_native_execution_receipt_guards_and_completed_lease(database, monkeypatch):  # noqa: F811
    connection, book, other = database
    before = read_identity_snapshot(connection, book)
    other_before = read_identity_snapshot(connection, other)
    plan = make_plan(before)
    monkeypatch.setattr(route, "BOOK", book)
    monkeypatch.setattr(route, "PLAN_SHA256", canonical_json_sha256(plan.model_dump()))
    monkeypatch.setattr(route, "WORK_KEY", "source-map:" + book + ":execution-test")
    receipt = route._execute_once(connection, plan, gate(), TREE, "1")
    assert receipt["committed"] is True
    after = read_identity_snapshot(connection, book)
    assert canonical_json_sha256(after["logical_row"]) == receipt["after_row_sha256"]
    assert all(after[k] == before[k] for k in route.GUARDS)
    assert read_identity_snapshot(connection, other) == other_before
    state = connection.execute("SELECT status,artifact_ref,artifact_sha256 FROM public.mls_source_map_work_leases WHERE work_key=%s", (route.WORK_KEY,)).fetchone()
    assert state[0] == "completed" and state[1].endswith("/actions/runs/1") and len(state[2]) == 64
    with pytest.raises(ValueError):
        route._execute_once(connection, plan, gate(), TREE, "1")
    assert read_identity_snapshot(connection, book) == after


@pytest.mark.parametrize("prior_status", ["expired", "released", "completed"])
def test_native_existing_key_rejects_before_identity_apply(database, monkeypatch, prior_status):  # noqa: F811
    connection, book, _ = database
    before = read_identity_snapshot(connection, book)
    plan = make_plan(before)
    monkeypatch.setattr(route, "BOOK", book)
    monkeypatch.setattr(route, "PLAN_SHA256", canonical_json_sha256(plan.model_dump()))
    monkeypatch.setattr(route, "WORK_KEY", "source-map:" + book + ":completed-test")
    lease = connection.execute("SELECT public.mls_claim_source_map_work(%s,%s,'test','test',%s,%s,600)",
                               (route.WORK_KEY, book, "0" * 64, "1" * 64)).fetchone()[0]
    if prior_status == "completed":
        connection.execute("SELECT public.mls_complete_source_map_work(%s,%s,'synthetic-only',%s)",
                           (route.WORK_KEY, lease["lease_token"], "2" * 64))
    elif prior_status == "released":
        connection.execute("SELECT public.mls_release_source_map_work(%s,%s)", (route.WORK_KEY, lease["lease_token"]))
    else:
        connection.execute("UPDATE public.mls_source_map_work_leases SET lease_expires_at=clock_timestamp()-interval '1 minute' WHERE work_key=%s", (route.WORK_KEY,))
    lease_before = connection.execute("SELECT to_jsonb(w) FROM public.mls_source_map_work_leases w WHERE work_key=%s", (route.WORK_KEY,)).fetchone()[0]
    with patch.object(route, "apply_identity_correction") as apply, pytest.raises(ValueError, match="never reclaim"):
        route._execute_once(connection, plan, gate(), TREE, "1")
    apply.assert_not_called()
    assert read_identity_snapshot(connection, book) == before
    assert connection.execute("SELECT to_jsonb(w) FROM public.mls_source_map_work_leases w WHERE work_key=%s", (route.WORK_KEY,)).fetchone()[0] == lease_before


def test_activation_workflow_has_no_pr_dispatch_or_rerun_write_route():
    workflow = yaml.load((Path(__file__).resolve().parents[1] / ".github/workflows/costanzo-identity-apply.yml").read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "env" not in workflow
    job = workflow["jobs"]["owner-gated-one-book-apply"]
    assert job["if"] == "github.ref == 'refs/heads/main' && github.run_attempt == 1"
    assert "env" not in job
    assert job["steps"][0]["with"] == {"ref": "${{ github.sha }}", "persist-credentials": "false"}
    assert len([s for s in job["steps"] if "env" in s]) == 1
