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


def latest_checkpoint(comments: Iterable[str]) -> SourceMapCheckpoint | None:
    materialized = list(comments)
    for comment in reversed(materialized):
        checkpoint = parse_checkpoint_block(comment)
        if checkpoint is not None:
            return checkpoint
    return None
