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



def test_draft_can_remain_pending_without_fake_review_evidence():
    pending = _COMPLETE.replace("Status: PASS", "Status: PENDING")
    assert module.validate(pending, ["scripts/check_pr_handoff.py"], draft=True) == []
    assert any(
        "PENDING" in error
        for error in module.validate(_COMPLETE, ["scripts/check_pr_handoff.py"], draft=True)
    )


def test_human_approval_requires_real_url_and_current_head():
    head = "1" * 40
    repo = "dnma28/medical-learning-system"
    body = _COMPLETE.replace(
        "https://github.com/dnma28/medical-learning-system/issues/186#issuecomment-123456",
        "https://github.com/dnma28/medical-learning-system/pull/190#pullrequestreview-42",
    )
    review = {
        "id": 42,
        "user": {"login": "reviewer", "type": "User"},
        "state": "APPROVED",
        "commit_id": head,
        "submitted_at": "2026-09-29T00:00:00Z",
    }
    check = lambda reviews, text=body: module.validate_independent_reviews(
        reviews, "author", head, body=text, repository=repo, number=190
    )
    assert check([review]) == []
    assert check([{**review, "commit_id": "2" * 40}])
    assert check([{**review, "user": {"login": "author", "type": "User"}}])
    assert check([{**review, "user": {"login": "bot", "type": "Bot"}}])
    assert check([review], body.replace("review-42", "review-0"))


def test_model_review_requires_real_comment_exact_head_and_distinct_session():
    head = "1" * 40
    writer = "sol-implementation-20260929"
    reviewer = "astra-review-20260929"
    body = _COMPLETE.replace(
        "https://github.com/dnma28/medical-learning-system/issues/186#issuecomment-123456",
        "https://github.com/dnma28/medical-learning-system/pull/190#pullrequestreview-43",
    ).replace("Status: PASS", f"Status: PASS\nMode: MODEL_INDEPENDENT\nWriter-Session: {writer}")
    review = {
        "id": 43,
        "user": {"login": "author", "type": "User"},
        "state": "COMMENTED",
        "commit_id": head,
        "submitted_at": "2026-09-29T00:01:00Z",
        "body": (
            "Model-Review: PASS\n"
            f"Reviewed-Commit: {head}\n"
            f"Writer-Session: {writer}\n"
            f"Reviewer-Session: {reviewer}\n"
            "Evidence-Checks: migration chain, source binding and exact CI contract\n"
            "Unresolved-Blocking-Findings: 0\n"
            "Summary: Independent model review found no blocking issue on this exact head.\n"
        ),
    }
    check = lambda reviews, text=body: module.validate_independent_reviews(
        reviews, "author", head, body=text,
        repository="dnma28/medical-learning-system", number=190,
    )
    assert check([review]) == []
    assert check([], body)
    assert check([review], body.replace("review-43", "review-0"))
    assert check([{**review, "commit_id": "2" * 40}])
    assert check([{**review, "body": review["body"].replace(reviewer, writer)}])
    assert check([{**review, "body": review["body"].replace("PASS", "BLOCKED")}])
    assert check([{**review, "body": review["body"].replace("Findings: 0", "Findings: 1")}])
    assert check([{**review, "body": review["body"].replace("migration chain, source binding and exact CI contract", "thin")}])
    later_blocked = {
        **review,
        "id": 44,
        "submitted_at": "2026-09-29T00:02:00Z",
        "body": review["body"].replace("Model-Review: PASS", "Model-Review: BLOCKED")
        .replace("Unresolved-Blocking-Findings: 0", "Unresolved-Blocking-Findings: 1"),
    }
    assert any("superseded" in error for error in check([review, later_blocked]))
    later_pass = {**review, "id": 45, "submitted_at": "2026-09-29T00:03:00Z"}
    assert any("superseded" in error for error in check([review, later_pass]))
