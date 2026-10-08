from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

psycopg = pytest.importorskip("psycopg")

from test_postgres_identity_correction import database  # noqa: F401

from medical_learning_system import identity_backend_preflight as preflight
from medical_learning_system.postgres_identity_correction import read_identity_snapshot


def test_workflow_keeps_production_credentials_on_main_backend_step_only():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/identity-backend-preflight.yml"
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push", "workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert "env" not in workflow
    job = workflow["jobs"]["read-only-connection"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert "env" not in job
    checkout = job["steps"][0]
    assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": "false"}
    secret_steps = [step for step in job["steps"] if "env" in step]
    assert len(secret_steps) == 1
    assert secret_steps[0]["run"] == "python -m medical_learning_system.identity_backend_preflight"


@pytest.mark.parametrize("url", [
    "", "http://ggwxpmwtvyptwbiuhhsl.supabase.co",
    "https://other-project.supabase.co", "https://ggwxpmwtvyptwbiuhhsl.supabase.co.evil.test",
    "https://user@ggwxpmwtvyptwbiuhhsl.supabase.co",
    "https://ggwxpmwtvyptwbiuhhsl.supabase.co:443",
    "https://ggwxpmwtvyptwbiuhhsl.supabase.co/x",
    "https://ggwxpmwtvyptwbiuhhsl.supabase.co?x=y",
    "https://ggwxpmwtvyptwbiuhhsl.supabase.co#x",
])
def test_wrong_target_rejected_before_connection(url):
    with pytest.raises(ValueError):
        preflight.connection_parameters({"MLS_SUPABASE_URL": url, "SUPABASE_DB_PASSWORD": "secret"})


def test_existing_secret_password_is_not_url_encoded_or_retargeted():
    value = "literal:@/? percent% password"
    parameters = preflight.connection_parameters({
        "MLS_SUPABASE_URL": "https://ggwxpmwtvyptwbiuhhsl.supabase.co/",
        "SUPABASE_DB_PASSWORD": value,
        "SUPABASE_POOLER_HOST": "evil.test",
    })
    assert parameters["password"] == value
    assert parameters["host"] == preflight.POOLER_HOST
    assert parameters["sslmode"] == "require"
    assert parameters["autocommit"] is True
    with pytest.raises(ValueError, match="missing"):
        preflight.connection_parameters({"MLS_SUPABASE_URL": "https://ggwxpmwtvyptwbiuhhsl.supabase.co"})


def test_summary_does_not_export_rows_or_book_content():
    connection = MagicMock()
    snapshot = {"logical_row": {"metadata": {"private": "hidden"}},
                "physical_sources": [{"x": "private-file-id"}],
                "staging_rows": [{"proposal": "copyrighted passage"}], "certificate_rows": []}
    with patch.object(preflight, "read_identity_snapshot", return_value=snapshot) as reader:
        result = preflight.snapshot_summary(connection)
    reader.assert_called_once_with(connection, "costanzo-physiology")
    calls = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
    assert calls[0].args == ("SET default_transaction_read_only = on",)
    assert result["production_apply_performed"] is False
    assert result["guard_counts"] == {"physical_sources": 1, "staging_rows": 1, "certificate_rows": 0}
    serialized = json.dumps(result)
    for private_value in ("hidden", "private-file-id", "copyrighted passage"):
        assert private_value not in serialized


def test_connection_failure_redacts_driver_details(monkeypatch, capsys):
    monkeypatch.setenv("MLS_SUPABASE_URL", "https://ggwxpmwtvyptwbiuhhsl.supabase.co")
    monkeypatch.setenv("SUPABASE_DB_PASSWORD", "never-print-this-password")
    with patch("psycopg.connect", side_effect=psycopg.OperationalError("never-print-this-password")):
        assert preflight.main() == 1
    output = capsys.readouterr().out
    assert "never-print-this-password" not in output
    assert "OperationalError" in output


def test_real_preflight_keeps_full_snapshot_and_rejects_writes(database, monkeypatch):  # noqa: F811
    connection, book, _ = database
    monkeypatch.setattr(preflight, "LOGICAL_SOURCE_ID", book)
    before = read_identity_snapshot(connection, book)
    result = preflight.snapshot_summary(connection)
    assert result["guard_counts"] == {
        "physical_sources": 2, "staging_rows": 2, "certificate_rows": 1,
    }
    assert result["snapshot_sha256"] == preflight.canonical_json_sha256(before)
    assert connection.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        connection.execute(
            "UPDATE public.mls_logical_sources SET title='forbidden' WHERE logical_source_id=%s",
            (book,),
        )
    assert read_identity_snapshot(connection, book) == before
