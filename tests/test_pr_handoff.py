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
Independent reviewer checks path classification.
## Risk and provenance
No source material or runtime writes.
## Gate evidence
Synthetic Source Map cases passed.
"""


def test_code_and_source_map_handoff_passes_with_all_fields():
    assert module.validate(_COMPLETE, ["scripts/check_pr_handoff.py"]) == []
    assert module.validate(_COMPLETE, ["src/medical_learning_system/source_map.py"]) == []


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
    assert any("No changed files" in error for error in module.validate(_COMPLETE, []))
