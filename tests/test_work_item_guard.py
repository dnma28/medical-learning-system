from medical_learning_system.work_item_guard import (
    WorkItem,
    audit_all,
    extract_work_key,
    is_managed_work_item,
    validate_current,
)


def item(number: int, body: str) -> WorkItem:
    return WorkItem(number=number, title=f"Issue {number}", body=body, url=f"https://x/{number}")


def managed_body(key: str | None) -> str:
    key_line = f"Work key: {key}\n" if key else ""
    return (
        "## Parent and outcome\n"
        f"{key_line}"
        "## Scope and inputs\n"
        "## Claim and handoff\n"
    )


def test_extract_work_key_normalizes_and_accepts_backticks():
    assert extract_work_key("Work key: `source-map:Magee-7e`") == "source-map:magee-7e"


def test_managed_item_requires_both_markers():
    assert is_managed_work_item(managed_body("code:guard"))
    assert not is_managed_work_item("Work key: code:guard")


def test_current_managed_issue_without_key_fails_closed():
    errors = validate_current([item(7, managed_body(None))], 7)
    assert "no valid 'Work key:'" in errors[0]


def test_duplicate_open_work_key_is_rejected():
    issues = [
        item(10, managed_body("source-map:magee")),
        item(11, managed_body("source-map:magee")),
    ]
    errors = validate_current(issues, 11)
    assert "Duplicate Work key 'source-map:magee'" in errors[0]
    assert "#10" in errors[0]


def test_distinct_frozen_child_keys_do_not_conflict():
    issues = [
        item(20, managed_body("source-map:neumann:part-1")),
        item(21, managed_body("source-map:neumann:part-3")),
    ]
    assert validate_current(issues, 21) == []
    assert audit_all(issues) == []


def test_audit_all_reports_every_duplicate_group():
    issues = [
        item(1, managed_body("source-map:magee")),
        item(2, managed_body("source-map:magee")),
        item(3, managed_body("code:router")),
        item(4, managed_body("code:router")),
    ]
    errors = audit_all(issues)
    assert errors == [
        "Duplicate Work key 'code:router': #3, #4.",
        "Duplicate Work key 'source-map:magee': #1, #2.",
    ]
