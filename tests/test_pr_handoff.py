import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_pr_handoff.py"
_spec = importlib.util.spec_from_file_location("check_pr_handoff", _SCRIPT)
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)

_COMPLETE = """## Issue
Closes #105
## Scope
Update the check and its tests.
## Verification
pytest -q tests/test_pr_handoff.py
## Review
Status: PASS
Commit: 1111111111111111111111111111111111111111
Evidence: https://github.com/dnma28/medical-learning-system/issues/186#issuecomment-123456
## Risk and provenance
No source material or runtime writes.
## Gate evidence
Synthetic Source Map cases passed.
"""


def test_code_and_source_map_handoff_passes_with_all_fields():
    head = "1" * 40
    assert module.validate(_COMPLETE, ["scripts/check_pr_handoff.py"], head) == []
    assert module.validate(
        _COMPLETE, ["src/medical_learning_system/source_map.py"], head
    ) == []


def test_missing_fields_fail_closed():
    errors = module.validate("## Issue\n<!-- placeholder -->\n", ["src/model.py"])
    assert any("## Scope" in error for error in errors)
    assert any("Risk and provenance" in error for error in errors)
    assert any("numbered GitHub issue" in error or "## Issue" in error for error in errors)


def test_docs_only_and_source_migration_gates():
    docs = _COMPLETE.split("## Risk and provenance")[0]
    assert module.validate(docs, ["docs/AI_WORK_QUEUE.md"]) == []
    assert any("Gate evidence" in error for error in module.validate(
        _COMPLETE.split("## Gate evidence")[0], ["supabase/migrations/0013.sql"]
    ))
    contract = ["docs/SOURCE_MAP_STAGING_PROMOTION.md"]
    missing = module.validate(_COMPLETE.split("## Risk and provenance")[0], contract)
    assert any("Risk and provenance" in error for error in missing)
    assert any("Gate evidence" in error for error in missing)
    assert any("No changed files" in error for error in module.validate(_COMPLETE, []))



def test_review_gate_rejects_pending_missing_evidence_and_stale_commit():
    pending = _COMPLETE.replace("Status: PASS", "Status: PENDING")
    assert any("Status: PASS" in error for error in module.validate(
        pending, ["src/model.py"], "1" * 40
    ))
    no_evidence = _COMPLETE.replace(
        "Evidence: https://github.com/dnma28/medical-learning-system/issues/186#issuecomment-123456\n",
        "",
    )
    assert any("evidence URL" in error for error in module.validate(
        no_evidence, ["src/model.py"], "1" * 40
    ))
    assert any("stale" in error for error in module.validate(
        _COMPLETE, ["src/model.py"], "2" * 40
    ))
