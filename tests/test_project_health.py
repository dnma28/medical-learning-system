from copy import deepcopy
from datetime import datetime, timezone

import pytest

from medical_learning_system.project_health import validate_snapshot

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def payload():
    return {
        "observed_at": NOW.isoformat(), "repository_sha": "a" * 40,
        "tasks": [{
            "id": "corpus", "status": "REVIEW_REQUIRED", "owner": "Astra",
            "authority": "https://github.com/example/repo/issues/1", "dependency": [],
            "evidence": [{"ref": "snapshot:1", "subject": "structure only",
                          "observed_at": NOW.isoformat()}],
            "blocking_reason": "retrieval unverified", "next_action": "verify retrieval",
            "definition_of_done": ["structure", "retrieval"],
            "passed_gates": {"structure": 0}, "last_verified_at": NOW.isoformat(),
        }],
    }


def test_structure_does_not_imply_completion():
    data = payload()
    assert validate_snapshot(data, as_of=NOW).tasks[0].status == "REVIEW_REQUIRED"
    data["tasks"][0].update(status="VERIFIED_DONE", blocking_reason=None)
    with pytest.raises(ValueError, match="every gate"):
        validate_snapshot(data, as_of=NOW)


def test_completion_requires_all_gate_references():
    data = payload()
    data["tasks"][0].update(status="VERIFIED_DONE", blocking_reason=None,
                            passed_gates={"structure": 0, "retrieval": 0})
    assert validate_snapshot(data, as_of=NOW).tasks[0].status == "VERIFIED_DONE"
    data["tasks"][0]["passed_gates"]["retrieval"] = True
    with pytest.raises(ValueError):
        validate_snapshot(data, as_of=NOW)


@pytest.mark.parametrize("kind", ["duplicate", "missing", "cycle", "unfinished"])
def test_dependency_invariants(kind):
    data = payload()
    task = data["tasks"][0]
    if kind == "duplicate":
        data["tasks"].append(deepcopy(task))
    elif kind == "missing":
        task["dependency"] = ["absent"]
    elif kind == "cycle":
        task["dependency"] = ["corpus"]
    else:
        child = deepcopy(task)
        child.update(id="child", status="VERIFIED_DONE", blocking_reason=None,
                     dependency=["corpus"], passed_gates={"structure": 0, "retrieval": 0})
        data["tasks"].append(child)
    with pytest.raises(ValueError):
        validate_snapshot(data, as_of=NOW)


@pytest.mark.parametrize("timestamp", ["2026-09-25T00:00:00Z", "2026-10-01T00:00:00Z",
                                       "2026-09-29T00:00:00"])
def test_stale_future_and_naive_timestamps_fail(timestamp):
    data = payload()
    data["observed_at"] = timestamp
    with pytest.raises(ValueError):
        validate_snapshot(data, as_of=NOW)


def test_unknown_needs_reason_and_old_task_cannot_hide_in_fresh_snapshot():
    data = payload()
    task = data["tasks"][0]
    task.update(status="UNKNOWN", blocking_reason=None)
    with pytest.raises(ValueError, match="reason"):
        validate_snapshot(data, as_of=NOW)
    task.update(blocking_reason="unread", last_verified_at="2026-09-25T00:00:00Z", evidence=[])
    task["passed_gates"] = {}
    with pytest.raises(ValueError, match="stale"):
        validate_snapshot(data, as_of=NOW)
