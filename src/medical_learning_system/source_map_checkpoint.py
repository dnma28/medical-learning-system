from __future__ import annotations

import json
import re
from typing import Any, Iterable

from pydantic import BaseModel, Field


CHECKPOINT_SCHEMA_VERSION = "1.0.0"
_CHECKPOINT_RE = re.compile(
    r"<!--\s*MLS_CHECKPOINT_BEGIN\s*(\{.*?\})\s*MLS_CHECKPOINT_END\s*-->",
    re.DOTALL,
)


class SourceMapCheckpoint(BaseModel):
    schema_version: str = CHECKPOINT_SCHEMA_VERSION
    work_key: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    cursor: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)



_CHECKPOINT_RANK = {
    "INPUT_FROZEN": 0,
    "SOURCE_READY": 1,
    "ARTIFACT_VERIFIED": 2,
    "VALIDATED": 3,
    "INDEPENDENT_REVIEW_PASS": 4,
    "READY_FOR_NEXT_ACTION": 5,
}


def validate_checkpoint_transition(
    previous: SourceMapCheckpoint | None,
    current: SourceMapCheckpoint,
) -> list[str]:
    errors: list[str] = []
    if previous is None:
        if current.status not in {"INPUT_FROZEN", "BLOCKED"}:
            errors.append("first checkpoint must be INPUT_FROZEN or BLOCKED")
        return errors

    for field in ("work_key", "book_id", "batch_id"):
        if getattr(previous, field) != getattr(current, field):
            errors.append(f"checkpoint {field} changed across one work stream")

    if previous.status != "BLOCKED" and current.status != "BLOCKED":
        if _CHECKPOINT_RANK.get(current.status, -1) < _CHECKPOINT_RANK.get(previous.status, -1):
            errors.append(
                f"checkpoint status regressed from {previous.status} to {current.status}"
            )
    return errors

def render_checkpoint_block(checkpoint: SourceMapCheckpoint) -> str:
    payload = json.dumps(
        checkpoint.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"<!-- MLS_CHECKPOINT_BEGIN\n{payload}\nMLS_CHECKPOINT_END -->"


def parse_checkpoint_block(text: str) -> SourceMapCheckpoint | None:
    match = _CHECKPOINT_RE.search(text)
    if match is None:
        return None
    return SourceMapCheckpoint.model_validate_json(match.group(1))


def latest_checkpoint(
    comments: Iterable[str],
    *,
    work_key: str | None = None,
    batch_id: str | None = None,
) -> SourceMapCheckpoint | None:
    materialized = list(comments)
    for comment in reversed(materialized):
        checkpoint = parse_checkpoint_block(comment)
        if checkpoint is None:
            continue
        if work_key is not None and checkpoint.work_key != work_key:
            continue
        if batch_id is not None and checkpoint.batch_id != batch_id:
            continue
        return checkpoint
    return None
