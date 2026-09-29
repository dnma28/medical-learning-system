"""Validate a dated read-only projection; never certify truth or mutate authorities."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    ref: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    observed_at: AwareDatetime


class TaskState(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1)
    status: Literal[
        "UNKNOWN", "NOT_STARTED", "IN_PROGRESS", "BLOCKED_SOURCE", "BLOCKED_CODE",
        "REVIEW_REQUIRED", "READY_FOR_PROMOTION", "VERIFIED_DONE",
    ]
    owner: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    dependency: list[str]
    evidence: list[Evidence]
    blocking_reason: str | None
    next_action: str = Field(min_length=1)
    definition_of_done: list[str] = Field(min_length=1)
    passed_gates: dict[str, StrictInt] = Field(default_factory=dict)
    last_verified_at: AwareDatetime

    @model_validator(mode="after")
    def check_gates(self):
        gates = self.definition_of_done
        if any(not gate.strip() for gate in gates) or len(set(gates)) != len(gates):
            raise ValueError("DONE gates must be nonempty and unique")
        if len(set(self.dependency)) != len(self.dependency):
            raise ValueError("duplicate dependency")
        if self.status in {"UNKNOWN", "BLOCKED_SOURCE", "BLOCKED_CODE"} and (
            not self.blocking_reason or not self.blocking_reason.strip()
        ):
            raise ValueError("unknown/blocked task requires a reason")
        for gate, index in self.passed_gates.items():
            if gate not in gates or not 0 <= index < len(self.evidence):
                raise ValueError("passed gate must reference a declared gate and evidence index")
        if any(e.observed_at > self.last_verified_at for e in self.evidence):
            raise ValueError("evidence is newer than task verification")
        if self.status == "VERIFIED_DONE" and (
            self.blocking_reason or set(self.passed_gates) != set(gates)
        ):
            raise ValueError("VERIFIED_DONE requires evidence for every gate and no blocker")
        return self


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    authority: Literal["derived_read_only"] = "derived_read_only"
    observed_at: AwareDatetime
    repository_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    tasks: list[TaskState] = Field(min_length=1)

    @model_validator(mode="after")
    def check_graph(self):
        tasks = {t.id: t for t in self.tasks}
        if len(tasks) != len(self.tasks):
            raise ValueError("duplicate task identity")
        visited, active = set(), set()

        def visit(task_id):
            if task_id not in tasks:
                raise ValueError("missing dependency")
            if task_id in active:
                raise ValueError("dependency cycle")
            if task_id in visited:
                return
            active.add(task_id)
            task = tasks[task_id]
            if task.last_verified_at > self.observed_at:
                raise ValueError("task verification is newer than snapshot")
            for dependency in task.dependency:
                visit(dependency)
                if task.status == "VERIFIED_DONE" and tasks[dependency].status != "VERIFIED_DONE":
                    raise ValueError("DONE task has unfinished dependency")
            active.remove(task_id)
            visited.add(task_id)

        for task_id in tasks:
            visit(task_id)
        return self


def validate_snapshot(payload, *, as_of=None, max_age_hours=24):
    """Check shape, dependency/gate references and freshness, not evidence authenticity."""
    now = as_of or datetime.now(timezone.utc)
    if now.utcoffset() is None or not 0 < max_age_hours <= 168:
        raise ValueError("aware as_of and max_age_hours in (0, 168] required")
    state = ProjectState.model_validate(payload)
    cutoff = now - timedelta(hours=max_age_hours)
    for timestamp in [state.observed_at, *(t.last_verified_at for t in state.tasks)]:
        if not cutoff <= timestamp <= now:
            raise ValueError("stale or future verification; refresh the affected authority")
    return state
